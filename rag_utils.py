import os

from dotenv import load_dotenv
from psycopg2 import pool
from sentence_transformers import SentenceTransformer


load_dotenv()


# ============================================================
# EMBEDDING MODEL
# ============================================================

embed_model = SentenceTransformer(
    "all-MiniLM-L6-v2"
)


# ============================================================
# DATABASE CONNECTION POOL
# ============================================================

db_pool = pool.SimpleConnectionPool(
    minconn=1,
    maxconn=5,
    dsn=os.getenv("DATABASE_URL"),
)


# ============================================================
# HYBRID SEARCH
# ============================================================

def hybrid_search(
    query,
    top_k=2,
    rrf_k=60,
    source_file=None,
):
    """
    Hybrid retrieval:

    1. Dense vector search
    2. PostgreSQL full-text keyword search
    3. Reciprocal Rank Fusion

    source_file:
        None  -> search across all indexed papers
        value -> search ONLY inside that paper
    """

    query_embedding = embed_model.encode(
        query
    ).tolist()

    conn = db_pool.getconn()

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            WITH vector_ranked AS (
                SELECT
                    id,
                    source_file,
                    chunk_index,
                    content,

                    ROW_NUMBER() OVER (
                        ORDER BY
                            embedding <=> %(qvec)s::vector
                    ) AS rank

                FROM document_chunks

                WHERE
                    (
                        %(source_file)s IS NULL
                        OR source_file = %(source_file)s
                    )
            ),

            keyword_ranked AS (
                SELECT
                    id,

                    ROW_NUMBER() OVER (
                        ORDER BY
                            ts_rank(
                                content_tsv,
                                plainto_tsquery(
                                    'english',
                                    %(query)s
                                )
                            ) DESC
                    ) AS rank

                FROM document_chunks

                WHERE
                    content_tsv @@ plainto_tsquery(
                        'english',
                        %(query)s
                    )

                    AND (
                        %(source_file)s IS NULL
                        OR source_file = %(source_file)s
                    )
            )

            SELECT
                v.source_file,
                v.chunk_index,
                v.content,

                (
                    (
                        1.0 / (
                            %(k)s + v.rank
                        )
                    )

                    +

                    COALESCE(
                        1.0 / (
                            %(k)s + k.rank
                        ),
                        0
                    )
                )::float AS score

            FROM vector_ranked v

            LEFT JOIN keyword_ranked k
                ON v.id = k.id

            ORDER BY score DESC

            LIMIT %(top_k)s;
            """,
            {
                "qvec": query_embedding,
                "query": query,
                "k": rrf_k,
                "top_k": top_k,
                "source_file": source_file,
            },
        )

        results = cursor.fetchall()

        cursor.close()

        return results

    finally:
        db_pool.putconn(conn)
