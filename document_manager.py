import io
import os
import re

import psycopg2
from pypdf import PdfReader

from rag_utils import embed_model


# ============================================================
# PAPER TITLES
# ============================================================

PAPER_TITLES = {
    "attention_is_all_you_need.pdf":
        "Attention Is All You Need (Transformer architecture)",

    "bert.pdf":
        "BERT: Pre-training of Deep Bidirectional Transformers",

    "vit.pdf":
        "An Image Is Worth 16x16 Words (Vision Transformer)",

    "lora.pdf":
        "LoRA: Low-Rank Adaptation of Large Language Models",

    "qlora.pdf":
        "QLoRA: Efficient Finetuning of Quantized LLMs",

    "gpt3.pdf":
        "Language Models Are Few-Shot Learners (GPT-3)",
}


# ============================================================
# UPLOAD CONFIG
# ============================================================

MAX_FILE_SIZE = 25 * 1024 * 1024

ALLOWED_EXTENSIONS = {
    ".pdf",
    ".md",
    ".txt",
}


# ============================================================
# HELPERS
# ============================================================

def clean_filename(filename: str) -> str:
    """
    Prevent path traversal and normalize uploaded filenames.
    """

    filename = os.path.basename(
        filename or ""
    ).strip()

    if not filename:
        raise ValueError(
            "A filename is required."
        )

    filename = re.sub(
        r"[^A-Za-z0-9._-]+",
        "_",
        filename,
    )

    return filename


def get_paper_title(filename: str) -> str:
    """
    Return known human-readable title.
    For newly uploaded papers, filename is used.
    """

    return PAPER_TITLES.get(
        filename.lower(),
        filename,
    )


# ============================================================
# TEXT EXTRACTION
# ============================================================

def extract_pdf_text(file_bytes: bytes) -> str:
    reader = PdfReader(
        io.BytesIO(file_bytes)
    )

    pages = []

    for page in reader.pages:
        page_text = page.extract_text() or ""

        if page_text.strip():
            pages.append(page_text)

    return "\n".join(pages)


def extract_text(
    filename: str,
    file_bytes: bytes,
) -> str:

    extension = os.path.splitext(
        filename
    )[1].lower()

    if extension == ".pdf":
        return extract_pdf_text(
            file_bytes
        )

    if extension in {
        ".md",
        ".txt",
    }:
        return file_bytes.decode(
            "utf-8",
            errors="replace",
        )

    raise ValueError(
        "Unsupported file type. "
        "Please upload a PDF, MD, or TXT file."
    )


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(text: str) -> str:
    text = re.sub(
        r"\n+",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# ============================================================
# CHUNKING
# ============================================================

def chunk_text(
    text,
    chunk_size=300,
    overlap=40,
):
    words = text.split()

    chunks = []

    start = 0

    step = chunk_size - overlap

    while start < len(words):

        chunk = " ".join(
            words[
                start:start + chunk_size
            ]
        )

        if chunk.strip():
            chunks.append(chunk)

        start += step

    return chunks


# ============================================================
# CHECK PAPER
# ============================================================

def paper_exists(
    conn,
    filename: str,
) -> bool:

    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT EXISTS(
                SELECT 1
                FROM document_chunks
                WHERE source_file = %s
            )
            """,
            (filename,),
        )

        return bool(
            cursor.fetchone()[0]
        )

    finally:
        cursor.close()


# ============================================================
# INSERT DOCUMENT
# ============================================================

def add_document(
    filename: str,
    file_bytes: bytes,
):
    """
    Add ONE document without deleting
    any existing documents.
    """

    filename = clean_filename(
        filename
    )

    extension = os.path.splitext(
        filename
    )[1].lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError(
            "Unsupported file type. "
            "Allowed: PDF, MD, TXT."
        )

    if not file_bytes:
        raise ValueError(
            "The uploaded file is empty."
        )

    if len(file_bytes) > MAX_FILE_SIZE:
        raise ValueError(
            "File is too large. "
            "Maximum size is 25 MB."
        )

    text = extract_text(
        filename,
        file_bytes,
    )

    text = clean_text(text)

    if not text:
        raise ValueError(
            "No readable text was found "
            "in the uploaded file."
        )

    raw_chunks = chunk_text(
        text,
        chunk_size=300,
        overlap=40,
    )

    if not raw_chunks:
        raise ValueError(
            "The document did not produce "
            "any usable chunks."
        )

    title = get_paper_title(
        filename
    )

    # Keep the same embedding strategy
    # as the existing ingest.py.
    contextual_chunks = [
        f"Paper: {title}\n\n{chunk}"
        for chunk in raw_chunks
    ]

    embeddings = embed_model.encode(
        contextual_chunks,
        show_progress_bar=False,
    )

    conn = psycopg2.connect(
        os.getenv("DATABASE_URL")
    )

    try:
        if paper_exists(
            conn,
            filename,
        ):
            raise FileExistsError(
                f"'{filename}' is already indexed."
            )

        cursor = conn.cursor()

        for idx, (
            raw_chunk,
            embedding,
        ) in enumerate(
            zip(
                raw_chunks,
                embeddings,
            )
        ):

            cursor.execute(
                """
                INSERT INTO document_chunks
                (
                    source_file,
                    chunk_index,
                    content,
                    embedding
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s
                )
                """,
                (
                    filename,
                    idx,
                    raw_chunk,
                    embedding.tolist(),
                ),
            )

        conn.commit()

        cursor.close()

        return {
            "filename": filename,
            "title": title,
            "chunks": len(raw_chunks),
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


# ============================================================
# LIST PAPERS
# ============================================================

def list_papers():
    """
    Return all unique indexed papers.
    """

    conn = psycopg2.connect(
        os.getenv("DATABASE_URL")
    )

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                source_file,
                COUNT(*) AS chunk_count
            FROM document_chunks
            GROUP BY source_file
            ORDER BY source_file;
            """
        )

        rows = cursor.fetchall()

        cursor.close()

        papers = []

        for (
            filename,
            chunk_count,
        ) in rows:

            papers.append(
                {
                    "filename": filename,
                    "title": get_paper_title(
                        filename
                    ),
                    "chunks": int(
                        chunk_count
                    ),
                }
            )

        return papers

    finally:
        conn.close()
