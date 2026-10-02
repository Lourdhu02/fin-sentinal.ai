"""Run the FinSentinelAI retrieval benchmark.

Indexes all 1,000 PDFs in test-data/sugar_dataset through the same parser,
chunker, embedder and ChromaDB store the app uses, then asks the questions in
eval/questions.jsonl and scores whether the gold document comes back at each
stage: dense, BM25, hybrid (RRF of both), and each of dense/hybrid after the
cross-encoder rerank. hybrid+rerank is the app's query path.

    python -m eval.run_eval                 # retrieval only
    python -m eval.run_eval --llm           # also score answers from Ollama

Writes eval/results/report.md and eval/results/results.json.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.metrics import answer_match, hit_at_k, mean, percentile, ranked_files, reciprocal_rank  # noqa: E402

DATASET = ROOT / "test-data" / "sugar_dataset"
QUESTIONS = ROOT / "eval" / "questions.jsonl"
RESULTS = ROOT / "eval" / "results"
SESSION = "eval"


def build_index(store, embedder, chunk_text, parser) -> tuple[int, int, float]:
    files = sorted(DATASET.rglob("*.pdf"))
    start = time.perf_counter()
    n_chunks = 0
    for path in files:
        chunks = chunk_text(parser.parse_path(path))
        store.add(embedder.embed_texts(chunks), [
            {"session_id": SESSION, "document_path": str(path), "text": chunk,
             "chunk_index": i, "file_name": path.name}
            for i, chunk in enumerate(chunks)
        ])
        n_chunks += len(chunks)
    return len(files), n_chunks, time.perf_counter() - start


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="FinSentinelAI retrieval benchmark")
    ap.add_argument("--llm", action="store_true", help="also generate answers with Ollama and score them")
    ap.add_argument("--allow-fallback", action="store_true",
                    help="run even without the embedding model (smoke test only; numbers are meaningless)")
    args = ap.parse_args(argv)

    os.environ.setdefault("FINSENTINEL_DATA_DIR", tempfile.mkdtemp(prefix="finsentinel-eval-"))
    from core.embedder import LocalEmbedder
    from core.ocr_parser import OCRParser
    from core.pipeline import FinSentinelPipeline
    from core.retriever import Retriever
    from database.vector_store import ChromaDBVectorStore

    embedder = LocalEmbedder()
    if embedder._model is None and not args.allow_fallback:
        print("Embedding model not loaded (hash fallback active); refusing to report numbers. "
              "Install sentence-transformers and allow the model download.", file=sys.stderr)
        return 2
    store = ChromaDBVectorStore(Path(os.environ["FINSENTINEL_DATA_DIR"]) / "chroma")
    retriever = Retriever(embedder, store)
    llm = None
    if args.llm:
        from core.llm_engine import OllamaEngine
        llm = OllamaEngine()

    n_docs, n_chunks, index_s = build_index(store, embedder, lambda t: FinSentinelPipeline._chunk_text(None, t), OCRParser())
    questions = [json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8").splitlines() if line.strip()]

    stages = ("dense", "bm25", "hybrid", "dense+rerank", "hybrid+rerank")
    flt = {"session_id": SESSION}
    rows = []
    for q in questions:
        question = q["question"]
        t0 = time.perf_counter()
        hybrid = retriever.hybrid_search(question, top_k=20, filter_dict=flt)
        app = retriever.rerank(question, hybrid, top_n=10)
        t1 = time.perf_counter()
        dense = store.search(embedder.embed_query(question), top_k=20, filter_dict=flt)
        ranked = {
            "dense": dense,
            "bm25": retriever.keyword_search(question, top_k=20, filter_dict=flt),
            "hybrid": hybrid,
            "dense+rerank": retriever.rerank(question, dense, top_n=10),
            "hybrid+rerank": app,
        }
        row = {**q, "total_ms": (t1 - t0) * 1000}
        for name in stages:
            files = ranked_files(ranked[name])
            row[f"{name}_files"] = files[:5]
            for k in (1, 5):
                row[f"{name}_hit@{k}"] = hit_at_k(files, q["gold_file"], k)
            row[f"{name}_rr"] = reciprocal_rank(files, q["gold_file"])
        if llm is not None:
            response = llm.generate(question, app, [], conversation_history=[])
            row["response"] = response
            row["answer_correct"] = answer_match(response, q["answer"])
        rows.append(row)

    def stage(name: str) -> dict:
        return {
            "recall@1": mean(r[f"{name}_hit@1"] for r in rows),
            "recall@5": mean(r[f"{name}_hit@5"] for r in rows),
            "mrr": mean(r[f"{name}_rr"] for r in rows),
        }

    lat = [r["total_ms"] for r in rows]
    summary = {
        "questions": len(rows), "documents": n_docs, "chunks": n_chunks,
        "index_seconds": round(index_s, 1),
        "embedding_model": embedder.model_name if embedder._model is not None else "HASH FALLBACK (not meaningful)",
        "reranker": "cross-encoder/ms-marco-MiniLM-L-6-v2" if retriever._reranker is not None else "none (model not loaded)",
        "stages": {name: stage(name) for name in stages},
        "latency_ms": {"p50": percentile(lat, 50), "p95": percentile(lat, 95)},
        "machine": f"{platform.system()} {platform.machine()}, {os.cpu_count()} CPUs, CPU-only",
    }
    if llm is not None:
        summary["answer_accuracy"] = mean(r["answer_correct"] for r in rows)
    by_type = {}
    for r in rows:
        by_type.setdefault(r["doc_type"], []).append(r)

    lines = [
        "# FinSentinelAI retrieval benchmark", "",
        f"{summary['questions']} questions over {n_docs} PDFs ({n_chunks} chunks), indexed in {summary['index_seconds']} s.",
        f"Embedder: `{summary['embedding_model']}` · reranker: `{summary['reranker']}` · {summary['machine']}.", "",
        "| stage | recall@1 | recall@5 | MRR |", "|---|---|---|---|",
    ]
    for name in stages:
        s = summary["stages"][name]
        lines.append(f"| {name} | {s['recall@1']:.1%} | {s['recall@5']:.1%} | {s['mrr']:.3f} |")
    lines += ["", f"App query path (hybrid + rerank) latency per query: p50 {summary['latency_ms']['p50']:.0f} ms, "
              f"p95 {summary['latency_ms']['p95']:.0f} ms.", ""]
    if llm is not None:
        lines += [f"Answer accuracy (gold value appears in the answer): {summary['answer_accuracy']:.1%}.", ""]
    lines += ["| document type | n | dense+rerank recall@5 | hybrid+rerank recall@1 | hybrid+rerank recall@5 |", "|---|---|---|---|---|"]
    for t, rs in by_type.items():
        lines.append(f"| {t} | {len(rs)} | {mean(r['dense+rerank_hit@5'] for r in rs):.0%} | "
                     f"{mean(r['hybrid+rerank_hit@1'] for r in rs):.0%} | {mean(r['hybrid+rerank_hit@5'] for r in rs):.0%} |")
    misses = [r for r in rows if not r["hybrid+rerank_hit@5"]]
    if misses:
        lines += ["", "## Misses (gold not in the app's top 5)", ""]
        lines += [f"- `{r['id']}` {r['question']} → gold `{r['gold_file']}`, got {r['hybrid+rerank_files'][:3]}" for r in misses]
    report = "\n".join(lines) + "\n"

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "report.md").write_text(report, encoding="utf-8")
    (RESULTS / "results.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=2), encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
