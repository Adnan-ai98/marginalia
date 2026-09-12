import os
import logging
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from google import genai
from google.genai.errors import APIError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import psycopg2

from rag_utils import hybrid_search

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rag_api")

# ---------- Startup validation: fail fast with a clear message ----------
required_env = ["DATABASE_URL", "GEMINI_API_KEY"]
missing = [k for k in required_env if not os.getenv(k)]
if missing:
    raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}. Check your .env file.")

app = FastAPI(title="RAG over ML Papers")
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# ---------- Rate limiting: protect the Gemini quota from abuse ----------
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


class Question(BaseModel):
    query: str = Field(..., min_length=3, max_length=500)
    top_k: int = Field(default=3, ge=1, le=10)


@app.get("/health")
def health_check():
    """Deployment platforms (Render, etc.) ping this to confirm the app + DB are alive."""
    try:
        conn = psycopg2.connect(os.getenv("DATABASE_URL"), connect_timeout=5)
        conn.close()
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        logger.error(f"Health check DB failure: {e}")
        return JSONResponse(status_code=503, content={"status": "degraded", "database": "unreachable"})


@app.post("/ask")
@limiter.limit("10/minute")
def ask(request: Request, payload: Question):
    # ---------- Retrieval ----------
    try:
        results = hybrid_search(payload.query, top_k=payload.top_k)
    except Exception as e:
        logger.error(f"Retrieval failed: {e}")
        raise HTTPException(status_code=503, detail="The document search is temporarily unavailable. Please try again shortly.")

    if not results:
        return {"answer": "No relevant information was found in the indexed documents for this question.", "sources": []}

    context_blocks = []
    sources = []
    for source_file, chunk_idx, content, score in results:
        context_blocks.append(f"[Source: {source_file}]\n{content}")
        sources.append({"file": source_file, "chunk": chunk_idx, "score": round(score, 4)})

    context = "\n\n---\n\n".join(context_blocks)

    prompt = f"""Answer the question using ONLY the context below. If the context doesn't contain the answer, say so clearly — do not make up information.

Context:
{context}

Question: {payload.query}

Answer:"""

    # ---------- Generation ----------
    try:
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt
        )
    except APIError as e:
        logger.error(f"Gemini API error: {e}")
        raise HTTPException(status_code=503, detail="The answer-generation service is temporarily unavailable. Please try again shortly.")
    except Exception as e:
        logger.error(f"Unexpected generation error: {e}")
        raise HTTPException(status_code=500, detail="Something went wrong generating the answer.")

    return {"answer": response.text, "sources": sources}


# ---------- Yeh sabse last mein honi chahiye ----------
app.mount("/", StaticFiles(directory="static", html=True), name="static")