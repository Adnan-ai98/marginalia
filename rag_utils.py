import os
from dotenv import load_dotenv
import psycopg2
from sentence_transformers import SentenceTransformer

load_dotenv()
embed_model = SentenceTransformer('all-MiniLM-L6-v2')

def hybrid_search(query, top_k=3, rrf_k=60):
    query_embedding = embed_model.encode(query).tolist()

    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cursor = conn.cursor()

    cursor.execute("""
        WITH vector_ranked AS (
            SELECT id, source_file, chunk_index, content,
                   ROW_NUMBER() OVER (ORDER BY embedding <=> %(qvec)s::vector) AS rank
            FROM document_chunks
        ),
        keyword_ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (ORDER BY ts_rank(content_tsv, plainto_tsquery('english', %(query)s)) DESC) AS rank
            FROM document_chunks
            WHERE content_tsv @@ plainto_tsquery('english', %(query)s)
        )
        SELECT v.source_file, v.chunk_index, v.content,
               (1.0 / (%(k)s + v.rank)) + COALESCE(1.0 / (%(k)s + k.rank), 0) AS score
        FROM vector_ranked v
        LEFT JOIN keyword_ranked k ON v.id = k.id
        ORDER BY score DESC
        LIMIT %(top_k)s;
    """, {"qvec": query_embedding, "query": query, "k": rrf_k, "top_k": top_k})

    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return results