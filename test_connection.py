import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()

try:
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cursor = conn.cursor()
    cursor.execute("SELECT version();")
    print("Connected! Postgres version:", cursor.fetchone())

    cursor.execute("SELECT * FROM pg_extension WHERE extname = 'vector';")
    result = cursor.fetchone()
    print("pgvector extension found:", result is not None)

    cursor.close()
    conn.close()
except Exception as e:
    print("Connection failed:", e)