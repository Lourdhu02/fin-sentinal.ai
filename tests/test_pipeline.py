import pytest

from core.pipeline import FinSentinelPipeline
from database.db_manager import DatabaseManager
from tests.helpers import Embedder, Vectors, Generator, Reranker


@pytest.fixture
def pipeline():
    db = DatabaseManager()
    db.create_user("alice", "hash")
    db.create_user("bob", "hash")
    return FinSentinelPipeline(db_manager=db, embedder=Embedder(), vector_store=Vectors(),
                               llm_engine=Generator(), retriever=Reranker())


def test_ingestion_query_isolation_and_idempotency(pipeline, tmp_path):
    path = tmp_path / "private.txt"
    path.write_text("Private invoice ZX900\nCurrency INR\nGrand Total: 123.45", encoding="utf-8")
    assert pipeline.ingest_and_store(path, "user_1_default", 1)["stored_count"] == 1
    count = len(pipeline.vector_store.items)
    pipeline.ingest_and_store(path, "user_1_default", 1)
    assert len(pipeline.vector_store.items) == count
    assert pipeline.query("ZX900", "user_2_default", 2)["results"] == []
    assert pipeline.query("ZX900", "user_1_default", 1)["results"][0]["page"] == 1
    pipeline.query("another", "user_2_default", 2)
    history = pipeline.llm_engine.calls[-1][2]
    assert all("Private invoice" not in turn["content"] for turn in history)


def test_empty_document_is_not_success(pipeline, tmp_path):
    path = tmp_path / "empty.txt"
    path.write_text("", encoding="utf-8")
    assert pipeline.ingest_and_store(path, "user_1_default", 1)["failed_count"] == 1
    assert pipeline.documents.get(1, path.name)["status"] == "failed"


def test_deletion_removes_evidence_and_history(pipeline, tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("Invoice ABC123", encoding="utf-8")
    pipeline.ingest_and_store(path, "user_1_default", 1)
    pipeline.query("ABC123", "user_1_default", 1)
    pipeline.delete_document("a.txt", 2)
    assert pipeline.documents.get(1, "a.txt")
    pipeline.delete_document("a.txt", 1)
    assert pipeline.documents.search(1, "ABC123") == []
    assert pipeline.vector_store.items == {}
    assert pipeline.conversations.history(1, "user_1_default") == []


def test_index_failure_is_recoverable(pipeline, tmp_path, monkeypatch):
    path = tmp_path / "a.txt"
    path.write_text("Invoice ABC123", encoding="utf-8")
    original = pipeline.vector_store.add
    monkeypatch.setattr(pipeline.vector_store, "add", lambda *args: (_ for _ in ()).throw(RuntimeError()))
    assert pipeline.ingest_and_store(path, "user_1_default", 1)["failed_count"] == 1
    assert pipeline.documents.search(1, "ABC123") == []
    monkeypatch.setattr(pipeline.vector_store, "add", original)
    assert pipeline.ingest_and_store(path, "user_1_default", 1)["stored_count"] == 1
