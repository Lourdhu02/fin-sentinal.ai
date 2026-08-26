"""Unit tests for FinSentinelPipeline.ingest_and_store and .query.

Runs the real pipeline against a temporary ChromaDB instance with a mocked
LLM engine (``RecordingLLM`` records every prompt and returns deterministic
responses, so no Ollama server is needed). Embeddings use the embedder's
deterministic hash fallback -- isolation and bookkeeping semantics under test
do not depend on semantic embedding quality.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from core.embedder import LocalEmbedder
from core.pipeline import FinSentinelPipeline
from database.db_manager import DatabaseManager
from database.vector_store import ChromaDBVectorStore

from tests.harness_support import RecordingLLM


SESSION_A = "user_101_default"
SESSION_B = "user_202_default"


@pytest.fixture()
def llm_spy() -> RecordingLLM:
    return RecordingLLM()


@pytest.fixture()
def pipeline(tmp_path: Path, llm_spy: RecordingLLM) -> FinSentinelPipeline:
    embedder = LocalEmbedder(model_name="test-offline-fallback")
    store = ChromaDBVectorStore(persist_dir=str(tmp_path / "chroma"))
    pipe = FinSentinelPipeline(
        db_manager=DatabaseManager(),
        embedder=embedder,
        vector_store=store,
        llm_engine=llm_spy,
    )
    pipe.retriever._reranker = None  # no cross-encoder downloads in unit tests
    return pipe


def _write_doc(directory: Path, name: str, body: str) -> Path:
    path = directory / name
    path.write_text(body, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# ingest_and_store
# ---------------------------------------------------------------------------
def test_ingest_stores_chunks_with_session_metadata(pipeline: FinSentinelPipeline, tmp_path: Path):
    doc = _write_doc(tmp_path, "invoice_a.txt", "Vendor A invoice\nSubtotal: 10\nTax: 1\nTotal: 11\n")

    summary = pipeline.ingest_and_store(doc, session_id=SESSION_A, user_id=101)

    assert summary["stored_count"] == 1
    assert summary["error_count"] == 0
    assert summary["documents"][0]["status"] == "stored"

    stored = pipeline.vector_store.collection.get(include=["metadatas"])
    metadatas = stored["metadatas"]
    assert metadatas, "Expected chunks to be persisted"
    for meta in metadatas:
        assert meta["session_id"] == SESSION_A
        assert meta["user_id"] == 101
        assert meta["file_name"] == "invoice_a.txt"
    assert [m["chunk_index"] for m in metadatas] == sorted(m["chunk_index"] for m in metadatas)


def test_ingest_without_user_id_omits_tag_but_keeps_session(pipeline: FinSentinelPipeline, tmp_path: Path):
    doc = _write_doc(tmp_path, "no_user.txt", "Anonymous content for storage.\n")

    summary = pipeline.ingest_and_store(doc, session_id=SESSION_A)

    assert summary["stored_count"] == 1
    for meta in pipeline.vector_store.collection.get(include=["metadatas"])["metadatas"]:
        assert meta["session_id"] == SESSION_A
        assert "user_id" not in meta  # ChromaDB rejects None values; tag omitted


def test_ingest_long_document_creates_multiple_chunks(pipeline: FinSentinelPipeline, tmp_path: Path):
    body = ("alpha ledger line\n" * 200)  # > chunk_size(700) after stripping
    doc = _write_doc(tmp_path, "long.txt", body)

    pipeline.ingest_and_store(doc, session_id=SESSION_A, user_id=101)

    metadatas = pipeline.vector_store.collection.get(include=["metadatas"])["metadatas"]
    assert len(metadatas) > 1
    assert {m["chunk_index"] for m in metadatas} == set(range(len(metadatas)))


def test_ingest_directory_with_no_supported_files_is_a_clean_noop(pipeline: FinSentinelPipeline, tmp_path: Path):
    (tmp_path / "binary.xyz").write_bytes(b"\x00\x01")

    summary = pipeline.ingest_and_store(tmp_path, session_id=SESSION_A, user_id=101)

    assert summary["processed_count"] == 0
    assert summary["stored_count"] == 0
    assert pipeline.vector_store.collection.count() == 0


# ---------------------------------------------------------------------------
# query
# ---------------------------------------------------------------------------
def test_query_returns_mock_response_and_session_filtered_results(
    pipeline: FinSentinelPipeline, tmp_path: Path, llm_spy: RecordingLLM
):
    pipeline.ingest_and_store(
        _write_doc(tmp_path, "a.txt", "Alpha vendor statement content.\n"),
        session_id=SESSION_A,
        user_id=101,
    )
    pipeline.ingest_and_store(
        _write_doc(tmp_path, "b.txt", "Beta vendor unrelated content.\n"),
        session_id=SESSION_B,
        user_id=202,
    )

    question = "What does alpha say?"
    result = pipeline.query(question, session_id=SESSION_A, user_id=101)

    assert result["response"] == f"[MOCK-ANSWER] {question}"
    assert result["query"] == question
    assert result["results"], "Expected at least one retrieved chunk"
    for item in result["results"]:
        assert item["session_id"] == SESSION_A

    # The prompt sent to the LLM contains only this session's evidence.
    assert len(llm_spy.prompts) == 1
    assert question in llm_spy.prompts[0]
    assert "Beta vendor" not in llm_spy.prompts[0]


def test_query_history_is_scoped_per_session(pipeline: FinSentinelPipeline, tmp_path: Path):
    pipeline.ingest_and_store(
        _write_doc(tmp_path, "shared.txt", "Neutral searchable content.\n"),
        session_id=SESSION_A,
        user_id=101,
    )
    # Same chunks visible per-session require separate ingests; B gets its own.
    pipeline.ingest_and_store(
        _write_doc(tmp_path, "shared_b.txt", "Neutral searchable content B.\n"),
        session_id=SESSION_B,
        user_id=202,
    )

    pipeline.query("first A question", session_id=SESSION_A, user_id=101)
    pipeline.query("second A question", session_id=SESSION_A, user_id=101)
    pipeline.query("only B question", session_id=SESSION_B, user_id=202)

    turns_a = pipeline.conversation_turns(SESSION_A)
    turns_b = pipeline.conversation_turns(SESSION_B)
    assert [t["content"] for t in turns_a] == [
        "first A question", "[MOCK-ANSWER] first A question",
        "second A question", "[MOCK-ANSWER] second A question",
    ]
    assert [t["content"] for t in turns_b] == [
        "only B question", "[MOCK-ANSWER] only B question",
    ]


def test_query_prompt_includes_prior_turns_of_same_session_only(
    pipeline: FinSentinelPipeline, tmp_path: Path, llm_spy: RecordingLLM
):
    pipeline.ingest_and_store(
        _write_doc(tmp_path, "ctx.txt", "Context for conversation tests.\n"),
        session_id=SESSION_A,
        user_id=101,
    )
    pipeline.query("opening question", session_id=SESSION_A, user_id=101)
    pipeline.query("follow up question", session_id=SESSION_A, user_id=101)

    second_prompt = llm_spy.prompts[1]
    assert "User: opening question" in second_prompt  # own history injected
    assert "Conversation History:" in second_prompt


def test_history_is_capped_at_twenty_turns(pipeline: FinSentinelPipeline, tmp_path: Path):
    pipeline.ingest_and_store(
        _write_doc(tmp_path, "cap.txt", "Cap test context.\n"),
        session_id=SESSION_A,
        user_id=101,
    )
    questions = [f"question number {i}" for i in range(11)]  # 22 turns -> capped
    for q in questions:
        pipeline.query(q, session_id=SESSION_A, user_id=101)

    turns = pipeline.conversation_turns(SESSION_A)
    assert len(turns) == 20
    assert turns[0]["content"] == questions[1]  # oldest surviving turn
    assert turns[-1]["content"] == f"[MOCK-ANSWER] {questions[-1]}"


def test_reset_conversation_clears_only_requested_session(pipeline: FinSentinelPipeline, tmp_path: Path):
    pipeline.ingest_and_store(
        _write_doc(tmp_path, "r.txt", "Reset test context.\n"),
        session_id=SESSION_A,
        user_id=101,
    )
    pipeline.query("A one", session_id=SESSION_A, user_id=101)
    pipeline.query("B one", session_id=SESSION_B, user_id=202)

    cleared = pipeline.reset_conversation(SESSION_A)

    assert cleared == 2
    assert pipeline.conversation_turns(SESSION_A) == []
    assert len(pipeline.conversation_turns(SESSION_B)) == 2


def test_reset_conversation_requires_session_id(pipeline: FinSentinelPipeline):
    with pytest.raises(ValueError):
        pipeline.reset_conversation("")


def test_query_on_empty_store_still_answers_from_fallback(
    pipeline: FinSentinelPipeline, llm_spy: RecordingLLM
):
    result = pipeline.query("anything?", session_id=SESSION_A, user_id=101)
    assert result["results"] == []
    assert result["response"] == "[MOCK-ANSWER] anything?"
    assert len(llm_spy.prompts) == 1
    assert "No retrieval context available." in llm_spy.prompts[0]


def test_sessions_are_isolated_by_unique_ids_not_by_content(pipeline: FinSentinelPipeline, tmp_path: Path):
    """Two sessions ingesting IDENTICAL text must still be isolated."""
    body = "Identical twin document contents.\n"
    pipeline.ingest_and_store(_write_doc(tmp_path, "twin.txt", body), session_id=SESSION_A, user_id=101)
    pipeline.ingest_and_store(_write_doc(tmp_path, "twin2.txt", body), session_id=SESSION_B, user_id=202)

    results = pipeline.vector_store.search(
        pipeline.retriever.embedder.embed_query("Identical twin"),
        top_k=50,
        filter_dict={"session_id": SESSION_A},
    )
    assert results
    assert all(r["session_id"] == SESSION_A for r in results)


@pytest.mark.parametrize("session", ["user_1_default", "user_2_default"])
def test_unique_sessions_get_unique_histories(pipeline: FinSentinelPipeline, tmp_path: Path, session: str):
    marker = f"q-{uuid.uuid4().hex[:6]}"
    pipeline.ingest_and_store(
        _write_doc(tmp_path, f"{session}.txt", "Param context.\n"), session_id=session, user_id=1
    )
    pipeline.query(marker, session_id=session, user_id=1)
    turns = pipeline.conversation_turns(session)
    assert turns and turns[0]["content"] == marker
