from rag_utils import hybrid_search

if __name__ == "__main__":
    test_queries = [
        "What was the final validation accuracy of the plant disease model?",
        "Why did full fine-tuning fail with an out of memory error?",
        "What LoRA rank was used for the Mistral model?",
    ]

    for q in test_queries:
        print(f"\n{'='*70}\nQUERY: {q}\n{'='*70}")
        for source, idx, content, score in hybrid_search(q):
            print(f"\n[{source} — chunk {idx} — score: {score:.4f}]")
            print(content[:200] + "...")