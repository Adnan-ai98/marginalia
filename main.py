import json
import logging
import os

import psycopg2

from dotenv import load_dotenv

from fastapi import (
    FastAPI,
    File,
    HTTPException,
    Request,
    UploadFile,
)

from fastapi.responses import (
    JSONResponse,
    StreamingResponse,
)

from fastapi.staticfiles import StaticFiles

from pydantic import (
    BaseModel,
    Field,
)

from slowapi import (
    Limiter,
    _rate_limit_exceeded_handler,
)

from slowapi.errors import (
    RateLimitExceeded,
)

from slowapi.util import (
    get_remote_address,
)

from document_manager import (
    add_document,
    list_papers,
)

from llm_router import (
    generate_answer_stream,
)

from rag_utils import (
    hybrid_search,
)


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
)

logger = logging.getLogger(
    "rag_api"
)


# ============================================================
# ENV VALIDATION
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
# APP
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
    _rate_limit_exceeded_handler,
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
        default=3,
        ge=1,
        le=10,
    )

    source_file: str | None = Field(
        default=None,
        max_length=255,
    )


# ============================================================
# HEALTH
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

    except Exception as e:

        logger.error(
            "Health check DB failure: %s",
            e,
        )

        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "database": "unreachable",
            },
        )


# ============================================================
# PAPERS
# ============================================================

@app.get("/papers")
def get_papers():

    try:

        papers = list_papers()

        return {
            "papers": papers
        }

    except Exception:

        logger.exception(
            "Failed to load papers"
        )

        raise HTTPException(
            status_code=503,
            detail=(
                "Could not load indexed papers."
            ),
        )


# ============================================================
# UPLOAD
# ============================================================

@app.post("/upload")
@limiter.limit("5/minute")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
):

    filename = file.filename or ""

    logger.info(
        "Upload started | filename=%s",
        filename,
    )

    try:

        file_bytes = await file.read()

        result = add_document(
            filename,
            file_bytes,
        )

        logger.info(
            "Upload completed | "
            "filename=%s | chunks=%d",
            result["filename"],
            result["chunks"],
        )

        return {
            "status": "success",
            **result,
        }

    except FileExistsError as e:

        logger.warning(
            "Duplicate upload | filename=%s",
            filename,
        )

        raise HTTPException(
            status_code=409,
            detail=str(e),
        )

    except ValueError as e:

        logger.warning(
            "Invalid upload | filename=%s | error=%s",
            filename,
            e,
        )

        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

    except Exception:

        logger.exception(
            "Document upload failed | filename=%s",
            filename,
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "The document could not be indexed."
            ),
        )


# ============================================================
# ASK
# ============================================================

@app.post("/ask")
@limiter.limit("10/minute")
def ask(
    request: Request,
    payload: Question,
):

    query = payload.query.strip()

    source_file = (
        payload.source_file.strip()
        if payload.source_file
        else None
    )

    logger.info(
        "Incoming question | query=%s | paper=%s",
        query,
        source_file or "ALL",
    )


    # ========================================================
    # 1. RETRIEVAL
    # ========================================================

    try:

        results = hybrid_search(
            query,
            top_k=payload.top_k,
            source_file=source_file,
        )

        logger.info(
            "Retrieved %d chunks | "
            "query=%s | paper=%s",
            len(results),
            query,
            source_file or "ALL",
        )

    except Exception:

        logger.exception(
            "Retrieval failed | query=%s",
            query,
        )

        raise HTTPException(
            status_code=503,
            detail=(
                "Search failed. "
                "Please try again."
            ),
        )


    # ========================================================
    # 2. NO RESULTS
    # ========================================================

    if not results:

        def empty_stream():

            yield (
                json.dumps(
                    {
                        "sources": [],
                        "status": "no_results",
                        "source_file": source_file,
                    }
                )
                + "\n---\n"
            )

            if source_file:

                yield (
                    "I couldn't find relevant "
                    "information in the selected paper."
                )

            else:

                yield (
                    "I couldn't find relevant "
                    "information in the indexed papers."
                )


        return StreamingResponse(
            empty_stream(),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )


    # ========================================================
    # 3. BUILD CONTEXT
    # ========================================================

    context_blocks = []

    sources = []


    for (
        result_source_file,
        chunk_idx,
        content,
        score,
    ) in results:

        context_blocks.append(
            f"[Source: {result_source_file}]\n"
            f"{content}"
        )

        sources.append(
            {
                "file": result_source_file,
                "chunk": chunk_idx,
                "score": round(
                    float(score),
                    4,
                ),
            }
        )


    context = "\n\n---\n\n".join(
        context_blocks
    )


    # ========================================================
    # 4. GROUNDED PROMPT
    # ========================================================

    if source_file:

        source_rule = f"""
SELECTED PAPER:
{source_file}

STRICT PAPER ISOLATION RULE:

The user selected ONE specific paper.

Answer ONLY from information contained
in the retrieved chunks from this selected paper.

Do NOT use information from any other paper.

Do NOT combine information from different papers.

If the selected paper does not contain enough
information to answer the question, say:

"I couldn't find that information in the selected paper."

Even if you know the answer from outside knowledge,
do NOT use it.
"""

    else:

        source_rule = """
PAPER SELECTION:
All indexed papers

Answer only from the retrieved context.
"""


    prompt = f"""
You are a RAG assistant answering questions
about foundational machine-learning research papers.

IMPORTANT RULES:

1. Answer ONLY using the supplied retrieved context.
2. Do not use outside knowledge.
3. Do not invent facts.
4. Preserve exact numbers, names,
   equations, and technical terminology.
5. Answer directly.
6. Keep the answer concise but technically accurate.
7. Do not mention your internal reasoning.
8. Do not mention "the supplied context".

{source_rule}

RETRIEVED CONTEXT:

{context}

USER QUESTION:

{query}

ANSWER:
"""


    logger.info(
        "Prepared Gemini prompt | "
        "context_chars=%d | "
        "sources=%d | "
        "paper=%s",
        len(context),
        len(sources),
        source_file or "ALL",
    )


    # ========================================================
    # 5. STREAM ANSWER
    # ========================================================

    def stream_response():

        yield (
            json.dumps(
                {
                    "sources": sources,
                    "status": "generating",
                    "source_file": source_file,
                }
            )
            + "\n---\n"
        )


        try:

            yield from generate_answer_stream(
                prompt
            )

            logger.info(
                "Answer stream completed | "
                "query=%s | paper=%s",
                query,
                source_file or "ALL",
            )

        except Exception:

            logger.exception(
                "Streaming generation failed | "
                "query=%s | paper=%s",
                query,
                source_file or "ALL",
            )

            yield (
                "\n\n"
                "Sorry, something went wrong while "
                "generating the answer. Please try again."
            )


    return StreamingResponse(
        stream_response(),
        media_type="text/plain",
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
