# quick_check.py naam se ek chhoti file banao
import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM document_chunks;")
print("Total rows:", cursor.fetchone())
cursor.close()
conn.close()