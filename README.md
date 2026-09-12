# Marginalia — RAG over Foundational ML Papers

A Retrieval-Augmented Generation (RAG) system that answers questions about six
foundational machine learning papers — grounded entirely in their text, with
every answer cited back to its source chunk. Built with FastAPI, PostgreSQL +
pgvector (via Supabase), hybrid (vector + keyword) search, and Gemini for
generation. Frontend is a themed dark "terminal" interface.

**Live demo:** https://marginalia-production-3c29.up.railway.app/
**Note:** hosted on Railway's free trial credit — if the link is down when
you're reading this, a demo recording is linked below instead.

**Demo**
!(marginalia_demo_v2.gif)
---

## What it does

Type a question about any of the six indexed papers (or click a sample
question) and get back an answer generated **only** from the retrieved
context — along with the exact source file and chunk it came from.

```
$ what is the scaled dot-product attention formula?

> Attention(Q, K, V) = softmax(QK^T / sqrt(d_k))V

attention_is_all_you_need.pdf #5   attention_is_all_you_need.pdf #6
```

## Indexed papers

| Paper | Topic |
|---|---|
| Attention Is All You Need | Transformer architecture |
| BERT | Bidirectional pre-training |
| An Image Is Worth 16x16 Words | Vision Transformer (ViT) |
| LoRA | Low-rank adaptation |
| QLoRA | 4-bit quantized fine-tuning |
| GPT-3 | Few-shot learning at scale |

~359 chunks total after ingestion.

## Architecture

```
Ingestion (once)
  PDFs → chunk (300 words, 40 overlap) → embed (sentence-transformers,
  384-dim) → store in Postgres/pgvector (Supabase)

Query (per request)
  Question → embed → hybrid search (vector cosine distance + Postgres
  full-text search, combined via Reciprocal Rank Fusion) → top-k chunks →
  Gemini (context-constrained prompt) → answer + cited sources
```

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Vector store | PostgreSQL + pgvector, hosted on Supabase | Managed, free tier, avoided a local pgvector compile on Windows |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` | Small (384-dim), fast, runs on CPU |
| Retrieval | Hybrid: `<=>` cosine distance + `tsvector`/`ts_rank`, fused with RRF | Pure vector search alone confused documents with similar structure (see below) |
| Backend | FastAPI | Async-ready, auto docs at `/docs`, easy to reason about |
| Generation | Gemini (`gemini-3.6-flash`) | Fast, generous free tier |
| Rate limiting | `slowapi` | Protects the Gemini quota once the app is public |
| Frontend | Vanilla HTML/CSS/JS, no framework | Small surface area, full control over the theme |

## Engineering notes — what actually broke, and why

This project went through two real, non-obvious bugs worth documenting
rather than hiding:

**1. Retrieval silently returned 0 rows for some queries, but not others.**
The `ivfflat` vector index was built with `lists = 100` on a table that, at
the time, had only 10 rows. `ivfflat` is an *approximate* index — it only
probes the single nearest cluster by default. With 100 near-empty clusters
and 10 rows, a query's nearest cluster was often empty, silently returning
nothing even though a perfect match existed elsewhere in the table. Fix:
dropped the index — exact search is trivially fast at this scale, and an
`ivfflat` index only makes sense once row count is in the thousands (rule of
thumb: `lists ≈ rows / 1000`).

**2. Pure vector search returned the wrong document for a specific-enough
query.** Asking "What LoRA rank was used for the Mistral model?" surfaced an
unrelated ViT model card ahead of the actual Mistral card. All the source
documents shared a near-identical Markdown structure (`# Model Card ##
Model Details | Field | Value |`), and the small embedding model picked up
on that structural similarity as much as the semantic content. Fix:
(a) injected each chunk with its parent document's title before embedding,
so the embedding carries document identity, and (b) added hybrid search —
combining dense vector retrieval with Postgres full-text keyword search via
Reciprocal Rank Fusion, so an exact term like "Mistral" pulls weight
alongside pure semantic similarity.

## Local setup

1. Clone this repo and create a virtual environment:
   ```
   python -m venv venv
   venv\Scripts\activate      # Windows
   pip install -r requirements.txt
   ```

2. Create a Supabase project, enable the `vector` extension (Database →
   Extensions), and grab the **Session pooler** connection string (not the
   Transaction pooler — see note below) from Project Settings → Database.

3. Get a Gemini API key from [Google AI Studio](https://aistudio.google.com).

4. Create a `.env` file:
   ```
   DATABASE_URL=postgresql://...supabase pooler connection string...
   GEMINI_API_KEY=your_key_here
   ```

5. Set up the schema (Supabase SQL editor):
   ```sql
   CREATE TABLE document_chunks (
       id BIGSERIAL PRIMARY KEY,
       source_file TEXT NOT NULL,
       chunk_index INT NOT NULL,
       content TEXT NOT NULL,
       embedding VECTOR(384)
   );

   ALTER TABLE document_chunks ADD COLUMN content_tsv tsvector
       GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;
   CREATE INDEX ON document_chunks USING GIN (content_tsv);
   ```

6. Drop your PDFs into `documents/`, then run:
   ```
   python ingest.py
   ```

7. Run the app:
   ```
   uvicorn main:app --reload
   ```
   Visit `http://localhost:8000`.

> **Why the Session pooler and not the Transaction pooler?** Supabase's
> Transaction-mode pooler (port 6543) can route successive queries within
> the same script to different backend connections, which caused
> intermittent, silently-empty results in early testing. The Session pooler
> (port 5432, still IPv4-compatible, avoiding a separate DNS/IPv6 issue)
> keeps one backend connection per script run and fixed it outright.

## API

- `POST /ask` — body: `{"query": "...", "top_k": 3}` → returns `{"answer": ..., "sources": [...]}`
- `GET /health` — checks the app and database are reachable
- Rate limited to 10 requests/minute per IP on `/ask`

## Known limitations

- Retrieval quality depends on chunk boundaries (fixed word-count chunks for
  PDFs, not semantic section splitting like the earlier Markdown-based
  version of this project).
- No conversation memory — every question is answered independently, with no
  awareness of prior turns.
- Free-tier Gemini and Render both impose rate/uptime constraints not
  suitable for real production traffic.

## Related projects

Part of the same fine-tuning/AI-engineering series as:
- `barakode-ai-roadmap` (CNN from scratch, Transformer from scratch, LoRA/QLoRA fine-tuning on Qwen + Mistral)
- `herbarium-plant-scanner` (LoRA-fine-tuned Vision Transformer + Flask interface)
