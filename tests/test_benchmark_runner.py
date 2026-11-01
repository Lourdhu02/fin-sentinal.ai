from types import SimpleNamespace

import pytest

from core.benchmarks.contracts import Catalog, Evidence, Judgment
from core.benchmarks.dataset import assign_groups
from core.benchmarks.files import sha256_file
from core.benchmarks.runner import evidence_recall, run_benchmark, summarize
from tests.test_benchmark_dataset import document


def fixture_inputs(tmp_path):
    source = tmp_path / "a.pdf"
    source.write_bytes(b"test source bytes; parser replaced in unit test")
    doc = document("a.pdf", layout=6, digest=sha256_file(source))
    catalog = Catalog(source_manifest_sha256="abc", documents=assign_groups([doc]))
    import hashlib
    text = "Invoice ZX900\nGrand Total: 12.34"
    evidence = Evidence(document_id=doc.document_id, page=1, start_char=8, end_char=13, quote="ZX900")
    judgment = Judgment(query_id="q1", question="Find invoice ZX900", category="invoices", partition="regression",
                         intent="identifier_lookup", evidence=[evidence])
    queue = {"schema_version": "review-queue-v1", "catalog_sha256": hashlib.sha256(catalog.model_dump_json().encode()).hexdigest(),
             "judgments": [judgment.model_dump()]}
    return catalog, queue, text


def test_draft_scores_are_opt_in(tmp_path):
    catalog, queue, _ = fixture_inputs(tmp_path)
    with pytest.raises(ValueError, match="allow-draft"):
        run_benchmark(catalog, queue, tmp_path)


def test_tampered_source_rejected(tmp_path):
    catalog, queue, _ = fixture_inputs(tmp_path)
    (tmp_path / "a.pdf").write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        run_benchmark(catalog, queue, tmp_path, allow_draft=True)


def test_actual_sql_retrieval_and_isolation(tmp_path, monkeypatch):
    catalog, queue, text = fixture_inputs(tmp_path)
    monkeypatch.setattr("core.benchmarks.runner.OCRParser.parse_pdf_pages",
                        lambda *args: [SimpleNamespace(page=1, text=text)])
    report = run_benchmark(catalog, queue, tmp_path, allow_draft=True)
    assert report["status"] == "completed"
    assert report["provisional"] is True
    assert report["release_gates_applied"] is False
    assert report["summary"]["metrics"]["recall"] == 1
    assert report["summary"]["metrics"]["evidence_recall"] == 1
    assert report["isolation_canary"]["lexical_leaks"] == 0
    assert report["isolation_canary"]["foreign_vector_hits_authorized"] == 0


def test_parse_failure_kept_in_denominator(tmp_path, monkeypatch):
    catalog, queue, _ = fixture_inputs(tmp_path)
    def fail(*args):
        raise ValueError("parser failed")
    monkeypatch.setattr("core.benchmarks.runner.OCRParser.parse_pdf_pages", fail)
    report = run_benchmark(catalog, queue, tmp_path, allow_draft=True)
    assert report["status"] == "completed_with_failures"
    assert report["summary"]["queries"] == report["summary"]["failed_queries"] == 1
    assert report["summary"]["metrics"]["recall"] == 0


def test_invalid_evidence_span_fails_run(tmp_path, monkeypatch):
    catalog, queue, text = fixture_inputs(tmp_path)
    queue["judgments"][0]["evidence"][0]["quote"] = "WRONG"
    monkeypatch.setattr("core.benchmarks.runner.OCRParser.parse_pdf_pages",
                        lambda *args: [SimpleNamespace(page=1, text=text)])
    with pytest.raises(ValueError, match="does not match"):
        run_benchmark(catalog, queue, tmp_path, allow_draft=True)


def test_span_requires_correct_page_and_complete_containment():
    evidence = [Evidence(document_id="a", page=2, start_char=10, end_char=20, quote="0123456789")]
    prediction = {"benchmark_document_id": "a", "page": 1, "start_char": 0, "end_char": 50}
    assert evidence_recall(evidence, [prediction]) == 0
    prediction.update(page=2, end_char=15)
    assert evidence_recall(evidence, [prediction]) == 0
    prediction["end_char"] = 25
    assert evidence_recall(evidence, [prediction]) == 1


def test_failed_rows_contribute_zero_to_aggregate():
    good = {"error": None, "latency_ms": 1, "metrics": {key: 1 for key in ["recall", "mrr", "ndcg", "evidence_recall"]}}
    bad = {"error": "failure", "latency_ms": 2, "metrics": {key: 0 for key in good["metrics"]}}
    assert summarize([good, bad])["metrics"]["recall"] == 0.5


def test_combined_profile_retains_partition_summaries(tmp_path, monkeypatch):
    catalog, queue, text = fixture_inputs(tmp_path)
    monkeypatch.setattr("core.benchmarks.runner.OCRParser.parse_pdf_pages",
                        lambda *args: [SimpleNamespace(page=1, text=text)])
    report = run_benchmark(catalog, queue, tmp_path, split="all_nonholdout", allow_draft=True)
    assert report["by_partition"]["regression"]["queries"] == 1


def test_dense_mode_does_not_silently_use_unpinned_model(tmp_path):
    catalog, queue, _ = fixture_inputs(tmp_path)
    with pytest.raises(ValueError, match="local embedding directory"):
        run_benchmark(catalog, queue, tmp_path, mode="dense", allow_draft=True)


@pytest.mark.parametrize("mode", ["dense", "hybrid"])
def test_optional_profiles_use_explicit_embedding_artifact(tmp_path, monkeypatch, mode):
    from tests.helpers import Embedder
    catalog, queue, text = fixture_inputs(tmp_path)
    artifact = tmp_path / "embedding"
    artifact.mkdir()
    (artifact / "fixture.bin").write_bytes(b"unit-test artifact; not a real model")
    monkeypatch.setattr("core.benchmarks.runner.OCRParser.parse_pdf_pages",
                        lambda *args: [SimpleNamespace(page=1, text=text)])
    monkeypatch.setattr("core.embedder.LocalEmbedder", lambda *args: Embedder())
    report = run_benchmark(catalog, queue, tmp_path, mode=mode, allow_draft=True, embedding_directory=artifact)
    assert report["embedding_artifact"]["files"] == 1
    assert report["configuration"]["dense_index"] == "numpy exact normalized dot product"
    assert report["summary"]["metrics"]["evidence_recall"] == 1
