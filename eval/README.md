# Retrieval benchmark

Measures whether FinSentinelAI's query path finds the right document. It uses
the same parser, chunker (700 characters, 120 overlap), embedder
(`all-MiniLM-L6-v2`), ChromaDB store and cross-encoder reranker
(`ms-marco-MiniLM-L-6-v2`) as the app.

- **Corpus:** all 1,000 PDFs in `test-data/sugar_dataset`: invoices, bank statements, salary slips, GST returns, purchase orders and credit/debit notes, in 10 layouts.
- **Questions:** [`questions.jsonl`](questions.jsonl), 60 questions (10 per document type) built by [`build_questions.py`](build_questions.py). Each gold answer is copied from its document's text, and each identifier in a question occurs in exactly one document of that type. CI regenerates the file and fails if it differs.
- **Metrics:** document-level recall@1, recall@5 and MRR for the dense stage (top 20) and after reranking (top 10); per-query retrieval latency (embed + search + rerank), CPU only. `--llm` also scores answers from a local Ollama model (gold value contained in the answer).

```bash
pip install -r requirements.txt
python -m eval.run_eval          # retrieval only, about 3-5 minutes on a laptop CPU
python -m eval.run_eval --llm    # with Ollama running
```

The report is written to `eval/results/report.md`. The harness refuses to
report numbers if the embedding model fails to load, because the app silently
falls back to random hash vectors in that case. The [Retrieval benchmark
workflow](../.github/workflows/eval.yml) runs it on every change to `eval/` or `core/`.
