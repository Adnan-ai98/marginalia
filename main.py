import os
import json
import logging

from dotenv import load_dotenv

from fastapi import (
    FastAPI,
    Request,
    HTTPException,
)

from fastapi.staticfiles import StaticFiles

from fastapi.responses import (
    JSONResponse,
    StreamingResponse,
)

from pydantic import (
    BaseModel,
    Field,
)

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

import psycopg2

from llm_router import generate_answer_stream
from rag_utils import hybrid_search


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(name)s | "
        "%(message)s"
    ),
)

logger = logging.getLogger(
    "rag_api"
)


# ============================================================
# ENVIRONMENT VALIDATION
# ============================================================

required_env = [
    "DATABASE_URL",
    "GEMINI_API_KEY",
]

missing = [
    key
    for key in required_env
    if not os.getenv(key)
]

if missing:

    raise RuntimeError(
        "Missing required environment variables: "
        + ", ".join(missing)
    )


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title="RAG over ML Papers"
)


# ============================================================
# RATE LIMITING
# ============================================================

limiter = Limiter(
    key_func=get_remote_address
)

app.state.limiter = limiter

app.add_exception_handler(
    RateLimitExceeded,
    lambda request, exc: JSONResponse(
        status_code=429,
        content={
            "detail": (
                "Too many requests. "
                "Please try again later."
            )
        },
    ),
)


# ============================================================
# REQUEST MODEL
# ============================================================

class Question(BaseModel):

    query: str = Field(
        ...,
        min_length=3,
        max_length=500,
    )

    top_k: int = Field(
        default=2,
        ge=1,
        le=10,
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
def health_check():

    try:

        conn = psycopg2.connect(
            os.getenv("DATABASE_URL"),
            connect_timeout=5,
        )

        conn.close()

        return {
            "status": "ok",
            "database": "connected",
        }


    except Exception:

        logger.exception(
            "Database health check failed"
        )

        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "database": "unreachable",
            },
        )


# ============================================================
# ASK ENDPOINT
# ============================================================

@app.post("/ask")
@limiter.limit("10/minute")
def ask(
    request: Request,
    payload: Question,
):

    query = payload.query.strip()


    logger.info(
        "Incoming question: %s",
        query,
    )


    # ========================================================
    # RETRIEVAL
    # ========================================================

    try:

        results = hybrid_search(
            query,
            top_k=payload.top_k,
        )


        logger.info(
            "Retrieved %d chunks | query=%s",
            len(results),
            query,
        )


    except Exception:

        logger.exception(
            "Retrieval failed | query=%s",
            query,
        )


        raise HTTPException(
            status_code=503,
            detail=(
                "Search service is temporarily "
                "unavailable. Please try again."
            ),
        )


    # ========================================================
    # NO RESULTS
    # ========================================================

    if not results:

        logger.warning(
            "No relevant documents found | query=%s",
            query,
        )


        def empty_stream():

            yield (
                json.dumps(
                    {
                        "sources": [],
                        "status": "no_results",
                    }
                )
                + "\n---\n"
            )


            yield (
                "I couldn't find relevant information "
                "in the indexed papers."
            )


        return StreamingResponse(
            empty_stream(),
            media_type=(
                "text/plain; charset=utf-8"
            ),
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )


    # ========================================================
    # BUILD CONTEXT
    # ========================================================

    context_blocks = []
    sources = []


    for (
        source_file,
        chunk_idx,
        content,
        score,
    ) in results:

        context_blocks.append(
            f"[Source: {source_file}]\n{content}"
        )


        sources.append(
            {
                "file": source_file,
                "chunk": chunk_idx,
                "score": round(
                    float(score),
                    4,
                ),
            }
        )


    context = (
        "\n\n---\n\n"
        .join(context_blocks)
    )


    # ========================================================
    # RAG PROMPT
    # ========================================================

    prompt = f"""
You are a RAG assistant answering questions about
foundational machine-learning research papers.

Answer the user's question using ONLY the retrieved
research-paper context below.

IMPORTANT RULES:

1. Use only the retrieved context.
2. Do not invent facts.
3. Do not use outside knowledge.
4. If the answer is not supported by the context,
   say that the information was not found in the
   indexed papers.
5. Answer the question directly.
6. Keep the answer concise but technically accurate.
7. Preserve important numbers, names, equations,
   and technical terminology.
8. Do not mention your internal reasoning.
9. Do not mention "the supplied context".

RETRIEVED RESEARCH CONTEXT:

{context}

USER QUESTION:

{query}

ANSWER:
"""


    logger.info(
        "Prepared Gemini prompt | "
        "context_chars=%d | sources=%d",
        len(context),
        len(sources),
    )


    # ========================================================
    # STREAM RESPONSE
    # ========================================================

    def stream_response():

        # Send sources first.
        yield (
            json.dumps(
                {
                    "sources": sources,
                    "status": "generating",
                }
            )
            + "\n---\n"
        )


        try:

            yield from generate_answer_stream(
                prompt
            )


            logger.info(
                "Answer stream completed | query=%s",
                query,
            )


        except Exception:

            logger.exception(
                "Unexpected generation failure | query=%s",
                query,
            )


            yield (
                "\n\n"
                "Sorry, something went wrong while "
                "generating the answer. Please try again."
            )


    return StreamingResponse(
        stream_response(),
        media_type=(
            "text/plain; charset=utf-8"
        ),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ============================================================
# STATIC FRONTEND
# ============================================================

app.mount(
    "/",
    StaticFiles(
        directory="static",
        html=True,
    ),
    name="static",
)
