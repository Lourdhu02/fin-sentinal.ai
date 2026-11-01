"""Execute isolated retrieval experiments against source-verified judgments."""
import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import time
import sys

from core.benchmarks.contracts import Catalog, Judgment
from core.benchmarks.files import read_json, sha256_file, source_path, write_json
from core.benchmarks.resources import Resources, percentile
from core.chunking import chunk_text
from core.evaluation import retrieval_metrics
from core.facts import extract_facts
from core.fusion import reciprocal_rank_fusion
from core.hardware import hardware_inventory
from core.ocr_parser import OCRParser


@contextmanager
def isolated_runtime(directory):
    from config import get_settings
    keys = {"FINSENTINEL_DATA_DIR": str(directory), "FINSENTINEL_DB_PATH": str(directory / "bench.db"),
            "FINSENTINEL_ENV": "development", "FINSENTINEL_OFFLINE": "1"}
    previous = {key: os.environ.get(key) for key in keys}
    os.environ.update(keys)
    get_settings.cache_clear()
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()


def validate_queue(catalog, queue, root, split, allow_draft):
    if queue.get("schema_version") != "review-queue-v1":
        raise ValueError("Unsupported judgment queue")
    digest = hashlib.sha256(catalog.model_dump_json().encode()).hexdigest()
    if queue.get("catalog_sha256") != digest:
        raise ValueError("Judgments belong to a different catalog")
    documents = {doc.document_id: doc for doc in catalog.documents}
    judgments = [Judgment.model_validate(item) for item in queue["judgments"]]
    if len({j.query_id for j in judgments}) != len(judgments):
        raise ValueError("Duplicate query IDs")
    selected = [j for j in judgments if j.partition == split or
                (split == "all_nonholdout" and j.partition != "holdout_candidate")]
    if not selected:
        raise ValueError("No judgments in requested partition")
    if not allow_draft and any(j.review_status != "human_reviewed" for j in selected):
        raise ValueError("Draft judgments require --allow-draft; release gates are disabled")
    # Verify immutable sources for every index candidate before scoring anything.
    for doc in catalog.documents:
        if doc.partition == "holdout_candidate" and split != "holdout_candidate":
            continue
        if sha256_file(source_path(root, doc.path)) != doc.sha256:
            raise ValueError(f"Source hash mismatch: {doc.path}")
    return selected, documents


def resolve_evidence(judgment, documents, parsed):
    for evidence in judgment.evidence:
        doc = documents.get(evidence.document_id)
        if doc is None or doc.partition != judgment.partition or doc.category != judgment.category:
            raise ValueError("Judgment evidence crosses category or partition")
        pages = parsed.get(doc.document_id)
        # A target parse failure remains a scored miss, not an excluded query.
        if pages is None:
            continue
        page = next((p for p in pages if p.page == evidence.page), None)
        if page is None or page.text[evidence.start_char:evidence.end_char] != evidence.quote:
            raise ValueError(f"Judgment evidence does not match source: {judgment.query_id}")


def evidence_recall(evidence, predictions):
    return sum(any(p["benchmark_document_id"] == e.document_id and p["page"] == e.page
                   and p["start_char"] <= e.start_char and p["end_char"] >= e.end_char
                   for p in predictions) for e in evidence) / len(evidence)


def summarize(rows):
    if not rows:
        return {"queries": 0, "metrics": None}
    keys = ["recall", "mrr", "ndcg", "evidence_recall"]
    return {"queries": len(rows), "failed_queries": sum(row["error"] is not None for row in rows),
            "metrics": {key: sum(row["metrics"][key] for row in rows) / len(rows) for key in keys},
            "retrieval_latency_ms": {"p50": percentile([r["latency_ms"] for r in rows], 0.5),
                                      "p95": percentile([r["latency_ms"] for r in rows], 0.95)}}


def environment():
    packages = {}
    for name in ("pdfplumber", "numpy", "sentence-transformers", "psutil", "pydantic"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    code = {"commit": None, "tracked_changes": None}
    try:
        root = Path(__file__).resolve().parents[2]
        code["commit"] = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                                        capture_output=True, text=True, check=True, timeout=3).stdout.strip()
        code["tracked_changes"] = bool(subprocess.run(["git", "status", "--porcelain", "-uno"], cwd=root,
                                        capture_output=True, text=True, check=True, timeout=3).stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    files = [Path(__file__).parents[1] / name for name in
             ("evaluation.py", "chunking.py", "facts.py", "ocr_parser.py", "fusion.py")]
    files += sorted(Path(__file__).parent.glob("*.py"))
    files += [Path(__file__).resolve().parents[2] / "database" / "documents.py"]
    code["implementation_sha256"] = hashlib.sha256("\n".join(
        f"{path.name}:{sha256_file(path)}" for path in files).encode()).hexdigest()
    return {"python": platform.python_version(), "packages": packages, "code": code,
            "hardware": hardware_inventory()}


def model_fingerprint(directory):
    if not directory.is_dir():
        raise ValueError("Dense/hybrid profiles require a provisioned local embedding directory")
    files = sorted(p for p in directory.rglob("*") if p.is_file())
    if not files:
        raise ValueError("Embedding directory is empty")
    digest = hashlib.sha256("\n".join(f"{p.relative_to(directory).as_posix()}:{sha256_file(p)}" for p in files).encode()).hexdigest()
    return {"directory_name": directory.name, "tree_sha256": digest, "files": len(files), "device": "cpu"}


def run_benchmark(catalog, queue, root, *, split="regression", mode="bm25", k=5,
                  allow_draft=False, allow_holdout=False, embedding_directory=None,
                  trace_python_heap=False, progress=None):
    if mode not in {"bm25", "dense", "hybrid"} or not 1 <= k <= 100:
        raise ValueError("Unsupported mode or k")
    if split == "holdout_candidate" and not allow_holdout:
        raise ValueError("Holdout scoring requires explicit --allow-holdout and consumes this holdout")
    if mode != "bm25" and embedding_directory is None:
        raise ValueError("Dense/hybrid profiles require a local embedding directory")
    judgments, documents = validate_queue(catalog, queue, root, split, allow_draft)
    selected = [d for d in catalog.documents if d.partition != "holdout_candidate" or split == "holdout_candidate"]
    report = {"schema_version": "benchmark-v1", "started_at": datetime.now(timezone.utc).isoformat(),
              "status": "running", "provisional": any(j.review_status == "draft" for j in judgments),
              "release_gates_applied": False,
              "label_scope": "identifier navigation; not general QA or financial accuracy",
              "catalog_sha256": hashlib.sha256(catalog.model_dump_json().encode()).hexdigest(),
              "judgments_sha256": hashlib.sha256(json.dumps(queue, sort_keys=True).encode()).hexdigest(),
              "configuration": {"mode": mode, "partition": split, "k": k, "chunk_size": 900,
                                "overlap": 120, "dense_index": "numpy exact normalized dot product" if mode != "bm25" else None,
                                "reranker": None, "generation": False, "index_scope": "all non-holdout documents" if split != "holdout_candidate" else "all documents"},
              "environment": environment(), "embedding_artifact": None}
    report["judgment_coverage"] = {
        "selected_documents": len(queue.get("selected_document_ids", [])),
        "candidate_failures": queue.get("candidate_failures", []),
        "scored_queries_in_partition": len(judgments),
        "note": "Candidate failures have no valid ground truth and are not retrieval queries; all corpus parse failures are reported separately",
    }
    if mode != "bm25":
        report["embedding_artifact"] = model_fingerprint(Path(embedding_directory or ""))
    parser = OCRParser(max_pdf_pages=200)
    parsed, chunks, failures, observations = {}, [], [], Counter()
    parse_started = time.perf_counter()
    with Resources(trace_python_heap=trace_python_heap) as resources:
        with tempfile.TemporaryDirectory(prefix="finsentinel-eval-") as temporary, isolated_runtime(Path(temporary)):
            from database.db_manager import DatabaseManager
            from database.documents import DocumentRepository
            db = DatabaseManager()
            try:
                alice = db.create_user("evaluation-reader", "not-a-login-hash").id
                bob = db.create_user("isolation-canary", "not-a-login-hash").id
                repository = DocumentRepository(db)
                indexing_seconds = 0
                for document_number, doc in enumerate(selected, 1):
                    try:
                        pages = parser.parse_pdf_pages(source_path(root, doc.path))
                        parsed[doc.document_id] = pages
                        facts = extract_facts(pages)
                        observations["documents_with_any_observed_amount"] += bool(facts["fields"])
                        observations["documents_with_explicit_currency"] += facts["currency"] is not None
                        stage = time.perf_counter()
                        registry_id, _ = repository.begin(alice, doc.path, doc.sha256)
                        batch = []
                        for page in pages:
                            for index, chunk in enumerate(chunk_text(page.text)):
                                chunk_id = hashlib.sha256(f"{registry_id}:{page.page}:{index}:chunks-v1".encode()).hexdigest()
                                batch.append({**chunk, "chunk_id": chunk_id, "document_id": registry_id,
                                    "benchmark_document_id": doc.document_id, "file_name": doc.path,
                                    "page": page.page, "user_id": alice, "session_id": f"user_{alice}_default"})
                        repository.save_chunks(alice, registry_id, batch, facts)
                        repository.status(alice, registry_id, "indexed")
                        chunks.extend(batch)
                        indexing_seconds += time.perf_counter() - stage
                    except Exception as exc:
                        failures.append({"document_id": doc.document_id, "error_type": type(exc).__name__})
                    if progress and document_number % 100 == 0:
                        progress(document_number, len(selected))
                report["corpus"] = {"documents": len(selected), "indexed_documents": len(selected) - len(failures),
                                    "chunks": len(chunks), "failures": failures}
                report["ingestion_seconds"] = time.perf_counter() - parse_started
                report["sqlite_index_seconds"] = indexing_seconds
                report["extraction_diagnostics"] = {**observations, "denominator": len(selected),
                    "accuracy": None, "reason": "No independently reviewed financial-field labels"}
                for judgment in judgments:
                    resolve_evidence(judgment, documents, parsed)
                embedder, matrix = None, None
                model_started = time.perf_counter()
                if mode != "bm25":
                    import numpy as np
                    from core.embedder import LocalEmbedder
                    embedder = LocalEmbedder(str(Path(embedding_directory).resolve()))
                    matrix = embedder.embed_texts([chunk["text"] for chunk in chunks])
                    if not chunks:
                        raise ValueError("Dense retrieval requires successfully indexed chunks")
                report["embedding_initialization_and_index_seconds"] = time.perf_counter() - model_started
                # A private token in another user's document must never be returned.
                token = "FINSENTINEL_CANARY_7C39E2"
                private_id, _ = repository.begin(bob, "canary.txt", "canary-hash")
                private_chunk = {"chunk_id": "canary-chunk", "text": token, "user_id": bob}
                repository.save_chunks(bob, private_id, [private_chunk], {})
                repository.status(bob, private_id, "indexed")
                leaked = repository.search(alice, token)
                authorized = repository.authorized_chunks(alice, [private_chunk])
                report["isolation_canary"] = {"lexical_leaks": len(leaked), "foreign_vector_hits_authorized": len(authorized),
                    "scope": "SQLite lexical filtering and authoritative vector-hit reauthorization; not a full security audit"}
                rows = []
                for judgment in judgments:
                    started = time.perf_counter()
                    error = None
                    predictions = []
                    try:
                        lexical = repository.search(alice, judgment.question, limit=100) if mode != "dense" else []
                        dense = []
                        if mode != "bm25":
                            query = embedder.embed_query(judgment.question)
                            scores = matrix @ query
                            order = np.argsort(-scores, kind="stable")[:100]
                            dense = [chunks[int(index)] for index in order]
                        predictions = reciprocal_rank_fusion(dense, lexical, limit=k) if mode == "hybrid" else (dense or lexical)[:k]
                    except Exception as exc:
                        error = type(exc).__name__
                    elapsed_ms = (time.perf_counter() - started) * 1000
                    expected = sorted({e.document_id for e in judgment.evidence})
                    # Missing target parses remain failed queries and scored misses.
                    if any(e.document_id not in parsed for e in judgment.evidence):
                        error = "TargetParseFailure"
                        predictions = []
                    metrics = retrieval_metrics(expected, [p["benchmark_document_id"] for p in predictions], k)
                    metrics["evidence_recall"] = evidence_recall(judgment.evidence, predictions)
                    rows.append({"query_id": judgment.query_id, "category": judgment.category, "partition": judgment.partition,
                                 "review_status": judgment.review_status, "metrics": metrics,
                                 "latency_ms": elapsed_ms, "error": error,
                                 "retrieved_document_ids": [p["benchmark_document_id"] for p in predictions],
                                 "retrieved_chunk_ids": [p["chunk_id"] for p in predictions]})
                report["summary"] = summarize(rows)
                report["by_category"] = {category: summarize([r for r in rows if r["category"] == category])
                                         for category in sorted({r["category"] for r in rows})}
                report["by_partition"] = {partition: summarize([r for r in rows if r["partition"] == partition])
                                          for partition in sorted({r["partition"] for r in rows})}
                report["queries"] = rows
                report["status"] = "completed_with_failures" if failures or any(r["error"] for r in rows) else "completed"
                if leaked or authorized:
                    report["status"] = "isolation_failure"
            finally:
                db.close()
    report["resources"] = resources.result
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--judgments", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--partition", choices=["development", "regression", "all_nonholdout", "holdout_candidate"], default="regression")
    parser.add_argument("--mode", choices=["bm25", "dense", "hybrid"], default="bm25")
    parser.add_argument("--embedding-directory", type=Path)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--allow-draft", action="store_true")
    parser.add_argument("--allow-holdout", action="store_true")
    parser.add_argument("--trace-python-heap", action="store_true")
    args = parser.parse_args()
    if args.mode != "bm25" and args.embedding_directory is None:
        parser.error("Dense/hybrid modes require --embedding-directory")
    if args.output.exists():
        parser.error("Output exists; choose a new artifact path")
    report = run_benchmark(Catalog.model_validate(read_json(args.catalog)), read_json(args.judgments), args.corpus,
                           split=args.partition, mode=args.mode, k=args.k, allow_draft=args.allow_draft,
                           allow_holdout=args.allow_holdout, embedding_directory=args.embedding_directory,
                           trace_python_heap=args.trace_python_heap,
                           progress=lambda done, total: print(f"Indexed {done}/{total}", file=sys.stderr))
    write_json(args.output, report)
    print(json.dumps({"status": report["status"], "provisional": report["provisional"],
                      "summary": report["summary"], "output": str(args.output)}, indent=2))
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
