import os
import json
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
from fastapi.responses import StreamingResponse
from google.genai import types
from llm_router import generate_answer_stream

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

    logger.info("Incoming question: %s", payload.query)

    # -------------------------
    # 1. RETRIEVAL
    # -------------------------
    try:
        results = hybrid_search(
            payload.query,
            top_k=payload.top_k
        )

        logger.info(
            "Retrieved %d chunks for query: %s",
            len(results),
            payload.query
        )

    except Exception as e:
        logger.exception("Retrieval failed")

        raise HTTPException(
            status_code=503,
            detail=f"Search failed: {str(e)}"
        )

    # -------------------------
    # 2. NO RESULTS
    # -------------------------
    if not results:

        def empty_stream():
            yield json.dumps({
                "sources": [],
                "status": "no_results"
            }) + "\n---\n"

            yield (
                "I couldn't find relevant information "
                "in the indexed papers."
            )

        return StreamingResponse(
            empty_stream(),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no"
            }
        )

    # -------------------------
    # 3. BUILD CONTEXT
    # -------------------------
    context_blocks = []
    sources = []

    for source_file, chunk_idx, content, score in results:

        context_blocks.append(
            f"[Source: {source_file}]\n{content}"
        )

        sources.append({
            "file": source_file,
            "chunk": chunk_idx,
            "score": round(float(score), 4)
        })

    context = "\n\n---\n\n".join(context_blocks)

    # -------------------------
    # 4. GROUNDED PROMPT
    # -------------------------
    prompt = f"""
You are a RAG assistant answering questions about
foundational machine-learning research papers.

IMPORTANT RULES:

1. Answer ONLY using the supplied context.
2. Do not use outside knowledge.
3. If the answer is not present in the context,
   say that it is not available in the indexed papers.
4. Answer directly.
5. Keep the answer concise and technically accurate.
6. Preserve exact numbers, names, and technical terminology
   from the source.
7. Do not mention "provided context".

CONTEXT:

{context}

QUESTION:

{payload.query}

ANSWER:
"""

    logger.info(
        "Sending %d characters of context to Gemini",
        len(context)
    )

    # -------------------------
    # 5. STREAM ANSWER
    # -------------------------
    def stream_response():

        yield json.dumps({
            "sources": sources,
            "status": "generating"
        }) + "\n---\n"

        try:
            yield from generate_answer_stream(prompt)

        except Exception as e:
            logger.exception("Streaming generation failed")

            yield (
                "\n[Generation failed: "
                + str(e)
                + "]"
            )

    return StreamingResponse(
        stream_response(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )
# ---------- Yeh sabse last mein honi chahiye ----------
app.mount("/", StaticFiles(directory="static", html=True), name="static")
