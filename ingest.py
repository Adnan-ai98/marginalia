import os
import re
from dotenv import load_dotenv
import psycopg2
from sentence_transformers import SentenceTransformer
from pypdf import PdfReader

load_dotenv()

print("Loading embedding model...")
embed_model = SentenceTransformer('all-MiniLM-L6-v2')

# Filename -> human-readable paper title (embedding context ke liye)
PAPER_TITLES = {
    "attention_is_all_you_need.pdf": "Attention Is All You Need (Transformer architecture)",
    "bert.pdf": "BERT: Pre-training of Deep Bidirectional Transformers",
    "vit.pdf": "An Image Is Worth 16x16 Words (Vision Transformer)",
    "lora.pdf": "LoRA: Low-Rank Adaptation of Large Language Models",
    "qlora.pdf": "QLoRA: Efficient Finetuning of Quantized LLMs",
    "gpt3.pdf": "Language Models Are Few-Shot Learners (GPT-3)",
}


def extract_pdf_text(path):
    reader = PdfReader(path)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text() or ""
        text += page_text + "\n"
    return text


def clean_text(text):
    text = re.sub(r'\n+', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def chunk_text(text, chunk_size=300, overlap=40):
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        chunks.append(' '.join(words[start:start + chunk_size]))
        start += chunk_size - overlap
    return chunks


def load_documents(folder="documents"):
    docs = []
    for filename in os.listdir(folder):
        path = os.path.join(folder, filename)
        if filename.endswith(".pdf"):
            raw_text = extract_pdf_text(path)
            docs.append((filename, clean_text(raw_text)))
        elif filename.endswith(".md"):
            with open(path, "r", encoding="utf-8") as f:
                docs.append((filename, f.read()))
    return docs


def main():
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cursor = conn.cursor()
    cursor.execute("DELETE FROM document_chunks;")

    docs = load_documents()
    print(f"Found {len(docs)} documents")

    total_chunks = 0
    for filename, content in docs:
        title = PAPER_TITLES.get(filename, filename)
        raw_chunks = chunk_text(content)
        print(f"  {filename} ('{title}'): {len(raw_chunks)} chunks")

        contextual_chunks = [f"Paper: {title}\n\n{chunk}" for chunk in raw_chunks]
        embeddings = embed_model.encode(contextual_chunks, show_progress_bar=True)

        for idx, (raw_chunk, embedding) in enumerate(zip(raw_chunks, embeddings)):
            cursor.execute(
                """INSERT INTO document_chunks (source_file, chunk_index, content, embedding)
                   VALUES (%s, %s, %s, %s)""",
                (filename, idx, raw_chunk, embedding.tolist())
            )
            total_chunks += 1

        conn.commit()   # har document ke baad commit — bada corpus hai, beech mein fail ho to progress na khoye

    cursor.close()
    conn.close()
    print(f"\nDone! {total_chunks} chunks embedded and stored.")


if __name__ == "__main__":
    main()