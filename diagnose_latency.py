import os
import time
import logging

from dotenv import load_dotenv

from rag_utils import hybrid_search
from llm_router import generate_answer_stream


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("latency_test")


# ============================================================
# TEST QUESTION
# ============================================================

QUESTION = "What is LoRA and how does it reduce trainable parameters?"

TOP_K = 2


# ============================================================
# START
# ============================================================

total_start = time.perf_counter()

print("\n" + "=" * 60)
print("        MARGINALIA LATENCY DIAGNOSTIC")
print("=" * 60)

print(f"\nQuestion: {QUESTION}")
print(f"Top K: {TOP_K}\n")


# ============================================================
# 1. RETRIEVAL
# ============================================================

print("[1/3] Testing RAG retrieval...")

retrieval_start = time.perf_counter()

try:

    results = hybrid_search(
        QUESTION,
        top_k=TOP_K,
    )

except Exception as e:

    print("\n❌ RETRIEVAL FAILED")
    print(f"Error: {e}")

    raise


retrieval_time = (
    time.perf_counter()
    - retrieval_start
)

print(
    f"✅ Retrieval completed: "
    f"{retrieval_time:.3f} seconds"
)

print(
    f"   Chunks retrieved: {len(results)}"
)


# ============================================================
# 2. CONTEXT PREPARATION
# ============================================================

print("\n[2/3] Preparing context...")

context_start = time.perf_counter()

context_blocks = []

for (
    source_file,
    chunk_idx,
    content,
    score,
) in results:

    context_blocks.append(
        f"[Source: {source_file}]\n{content}"
    )


context = (
    "\n\n---\n\n"
    .join(context_blocks)
)


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

RETRIEVED RESEARCH CONTEXT:

{context}

USER QUESTION:

{QUESTION}

ANSWER:
"""


context_time = (
    time.perf_counter()
    - context_start
)

print(
    f"✅ Context preparation: "
    f"{context_time:.3f} seconds"
)

print(
    f"   Context size: {len(context):,} characters"
)


# ============================================================
# 3. GEMINI GENERATION
# ============================================================

print("\n[3/3] Testing Gemini generation...")
print("Waiting for first token...\n")

generation_start = time.perf_counter()

first_token_time = None
total_generated = 0

try:

    for chunk in generate_answer_stream(prompt):

        if first_token_time is None:

            first_token_time = (
                time.perf_counter()
                - generation_start
            )

            print(
                f"🚀 First token received: "
                f"{first_token_time:.3f} seconds"
            )

        total_generated += len(chunk)

        print(
            chunk,
            end="",
            flush=True,
        )


except Exception as e:

    print("\n\n❌ GENERATION FAILED")
    print(f"Error: {e}")

    raise


generation_time = (
    time.perf_counter()
    - generation_start
)


# ============================================================
# TOTAL
# ============================================================

total_time = (
    time.perf_counter()
    - total_start
)


print("\n\n" + "=" * 60)
print("                 RESULTS")
print("=" * 60)

print(
    f"\nRetrieval time:       {retrieval_time:.3f}s"
)

print(
    f"Context preparation:  {context_time:.3f}s"
)

if first_token_time is not None:

    print(
        f"Gemini first token:   {first_token_time:.3f}s"
    )

else:

    print(
        "Gemini first token:   N/A"
    )


print(
    f"Gemini total:         {generation_time:.3f}s"
)

print(
    f"Total test time:      {total_time:.3f}s"
)

print(
    f"Generated characters: {total_generated}"
)


# ============================================================
# DIAGNOSIS
# ============================================================

print("\n" + "=" * 60)
print("                 DIAGNOSIS")
print("=" * 60)


if retrieval_time >= 3:

    print(
        "\n⚠️ Retrieval is relatively slow."
    )

elif retrieval_time >= 1:

    print(
        "\n🟡 Retrieval has noticeable latency."
    )

else:

    print(
        "\n🟢 Retrieval looks fast."
    )


if first_token_time is not None:

    if first_token_time >= 5:

        print(
            "🔴 Gemini first-token latency is high."
        )

    elif first_token_time >= 2:

        print(
            "🟡 Gemini first-token latency is noticeable."
        )

    else:

        print(
            "🟢 Gemini first-token latency looks good."
        )


print("\n" + "=" * 60)
print("Diagnostic complete.")
print("=" * 60 + "\n")
