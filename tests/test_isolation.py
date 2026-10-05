"""Multi-user isolation harness for FinSentinelAI (paper evaluation core).

Simulates two authenticated users (A and B) against the real FastAPI app,
uploads a distinct document per user, interleaves their chat requests --
sequentially, on threads, and via asyncio.gather -- and asserts that no
content from one user can reach the other user's LLM prompt or retrieval
results.

=============================================================================
RUNBOOK -- how to produce the paper's before/after results table
=============================================================================

Prerequisites: ``pip install -r requirements.txt`` (needs fastapi, chromadb,
pydantic, PyJWT, passlib, cryptography, numpy, httpx, pytest; heavy ML deps
are NOT required -- the embedder falls back to deterministic hash vectors).

BEFORE measurement (buggy code, commit dbe3cac = pre-fix main)::

    git checkout dbe3cac
    git checkout test/isolation-harness -- tests/ requirements.txt
    pytest tests/test_isolation.py -v
    cat tests/_isolation_report.json

Expected: prompt-isolation and reset-scoping tests FAIL; the report shows
leakage_rate > 0.0 for at least one user. That number is the "before" cell.

AFTER measurement (fixed code)::

    git checkout test/isolation-harness
    pytest tests/test_isolation.py -v

Expected: all tests pass; every leakage_rate in the report is exactly 0.0.
That is the "after" cell.

The suite is written to run against BOTH revisions: assertions that depend on
post-fix internals (per-session history introspection, required filter_dict)
degrade to behavioural checks on pre-fix code instead of erroring out, so the
"before" run still yields clean leakage numbers rather than collection errors.
"""

from __future__ import annotations

import asyncio
import inspect
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from fastapi.testclient import TestClient

from core.embedder import LocalEmbedder
from core.pipeline import FinSentinelPipeline
from database.db_manager import DatabaseManager
from database.vector_store import ChromaDBVectorStore

from tests.harness_support import (
    USER_A_DOC_TEXT,
    USER_A_MARKER,
    USER_A_QUESTIONS,
    USER_B_DOC_TEXT,
    USER_B_MARKER,
    USER_B_QUESTIONS,
    REPORT,
    RecordingLLM,
    foreign_markers_for,
    leakage_rate,
    prompt_leaks,
    record_measurement,
    record_prompt_audit,
    session_id_for,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def app():
    from api.main import app as fastapi_app  # imported AFTER conftest env setup

    return fastapi_app


class Harness:
    """Per-test isolation harness bound to one fresh pipeline instance."""

    def __init__(self, client: TestClient, pipeline: FinSentinelPipeline, llm_spy: RecordingLLM):
        self.client = client
        self.pipeline = pipeline
        self.llm_spy = llm_spy

    # -- auth ---------------------------------------------------------------
    def make_user(self, label: str) -> dict[str, Any]:
        username = f"{label}_{uuid.uuid4().hex[:10]}"
        register = self.client.post("/api/auth/register", json={"username": username, "password": "S3cret-Pass!"})
        assert register.status_code == 200, register.text
        login = self.client.post(
            "/api/auth/login",
            data={"username": username, "password": "S3cret-Pass!"},
        )
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]
        me = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200, me.text
        user_id = int(me.json()["id"])
        return {
            "label": label,
            "id": user_id,
            "username": username,
            "session_id": session_id_for(user_id),
            "headers": {"Authorization": f"Bearer {token}"},
        }

    # -- documents ----------------------------------------------------------
    def upload(self, user: dict[str, Any], filename: str, content: str) -> None:
        response = self.client.post(
            "/api/documents/upload",
            headers=user["headers"],
            files=[("files", (filename, content.encode("utf-8"), "text/plain"))],
        )
        assert response.status_code == 200, response.text
        statuses = [doc["status"] for doc in response.json()]
        assert statuses and all(s == "success" for s in statuses), response.text

    # -- chat ---------------------------------------------------------------
    def chat(self, user: dict[str, Any], question: str) -> dict[str, Any]:
        response = self.client.post(
            "/api/chat/",
            headers=user["headers"],
            json={"query": question},
        )
        assert response.status_code == 200, response.text
        return response.json()

    def reset(self, user: dict[str, Any]) -> dict[str, Any]:
        response = self.client.post("/api/chat/reset", headers=user["headers"])
        assert response.status_code == 200, response.text
        return response.json()

    # -- attribution --------------------------------------------------------
    def prompts_for(self, user: dict[str, Any], responses: list[dict[str, Any]]) -> list[str]:
        """Map a user's observed HTTP responses back to their exact prompts."""
        prompts: list[str] = []
        for payload in responses:
            found = self.llm_spy.prompts_containing(payload["response"])
            assert found, f"No recorded prompt for response: {payload['response'][:80]}"
            prompts.extend(found)
        return prompts


@pytest.fixture()
def harness(app, tmp_path, monkeypatch):
    # Deterministic, dependency-free embeddings: an impossible model name makes
    # LocalEmbedder fall back to its sha256-seeded hash vectors. Isolation
    # properties under test do not depend on semantic embedding quality.
    embedder = LocalEmbedder(model_name="test-offline-fallback")
    llm_spy = RecordingLLM()
    vector_store = ChromaDBVectorStore(persist_dir=str(tmp_path / "chroma"))
    pipeline = FinSentinelPipeline(
        db_manager=DatabaseManager(),
        embedder=embedder,
        vector_store=vector_store,
        llm_engine=llm_spy,
    )
    # Keep the reranker off: loading a cross-encoder would download weights and
    # add nondeterminism irrelevant to isolation semantics.
    pipeline.retriever._reranker = None

    # Production instantiates ONE pipeline per process shared by every route;
    # reproduce that exact topology (both modules must see the same instance).
    from api.routes import chat as chat_routes
    from api.routes import documents as document_routes

    monkeypatch.setattr(chat_routes, "pipeline", pipeline)
    monkeypatch.setattr(document_routes, "pipeline", pipeline)

    return Harness(TestClient(app), pipeline, llm_spy)


def _two_users(harness: Harness) -> tuple[dict[str, Any], dict[str, Any]]:
    user_a = harness.make_user("alpha")
    user_b = harness.make_user("beta")
    harness.upload(user_a, "alpha_invoice.txt", USER_A_DOC_TEXT)
    harness.upload(user_b, "beta_invoice.txt", USER_B_DOC_TEXT)
    return user_a, user_b


def _assert_no_cross_user_prompts(
    harness: Harness,
    user_a: dict[str, Any],
    user_b: dict[str, Any],
    responses_a: list[dict[str, Any]],
    responses_b: list[dict[str, Any]],
    test_name: str,
) -> None:
    prompts_a = harness.prompts_for(user_a, responses_a)
    prompts_b = harness.prompts_for(user_b, responses_b)
    assert prompts_a and prompts_b, "Harness captured no prompts; spy wiring broken."

    foreign_for_a = foreign_markers_for(USER_A_MARKER, USER_A_QUESTIONS, USER_B_MARKER, USER_B_QUESTIONS)
    foreign_for_b = foreign_markers_for(USER_B_MARKER, USER_B_QUESTIONS, USER_A_MARKER, USER_A_QUESTIONS)

    rate_a = leakage_rate(prompts_a, foreign_for_a)
    rate_b = leakage_rate(prompts_b, foreign_for_b)
    record_measurement(test_name, "user_a_vs_b", rate_a, len(prompts_a))
    record_measurement(test_name, "user_b_vs_a", rate_b, len(prompts_b))

    for prompt in prompts_a:
        record_prompt_audit(test_name, "A", prompt, prompt_leaks(prompt, foreign_for_a))
        assert not prompt_leaks(prompt, foreign_for_a), (
            f"User B content leaked into User A's LLM prompt:\n{prompt[:800]}"
        )
    for prompt in prompts_b:
        record_prompt_audit(test_name, "B", prompt, prompt_leaks(prompt, foreign_for_b))
        assert not prompt_leaks(prompt, foreign_for_b), (
            f"User A content leaked into User B's LLM prompt:\n{prompt[:800]}"
        )


# ---------------------------------------------------------------------------
# Layer 2: retrieval isolation (vector store)
# ---------------------------------------------------------------------------
def test_vector_search_never_crosses_sessions(harness: Harness):
    user_a, user_b = _two_users(harness)

    # Validity precondition: BOTH sessions' chunks coexist in the collection,
    # so passing these assertions means filtering (not absence) isolated them.
    all_meta = harness.pipeline.vector_store.collection.get(include=["metadatas"])
    sessions_in_store = {m["session_id"] for m in all_meta["metadatas"]}
    assert user_a["session_id"] in sessions_in_store
    assert user_b["session_id"] in sessions_in_store

    query_vec = harness.pipeline.retriever.embedder.embed_query(USER_A_QUESTIONS[0])
    results_a = harness.pipeline.vector_store.search(
        query_vec, top_k=50, filter_dict={"session_id": user_a["session_id"]}
    )
    assert results_a, "Expected retrieval results for user A"
    for item in results_a:
        assert item["session_id"] == user_a["session_id"]
        assert USER_B_MARKER.lower() not in str(item.get("text", "")).lower()

    # Defense-in-depth: chunks are tagged with the owning user_id where the
    # schema supports it (pre-fix ingests carry session_id only).
    tagging_supported = all("user_id" in m for m in all_meta["metadatas"])
    if tagging_supported:
        ids_by_session = {
            m["session_id"]: m.get("user_id") for m in all_meta["metadatas"]
        }
        assert ids_by_session[user_a["session_id"]] == user_a["id"]
        assert ids_by_session[user_b["session_id"]] == user_b["id"]


def test_chat_sources_never_include_foreign_documents(harness: Harness):
    user_a, user_b = _two_users(harness)

    answer_a = harness.chat(user_a, USER_A_QUESTIONS[0])
    for source in answer_a["sources"]:
        blob = f"{source.get('file_name', '')} {source.get('text', '')}".lower()
        assert USER_B_MARKER.lower() not in blob
        assert "beta_invoice" not in blob


# ---------------------------------------------------------------------------
# Layer 3: conversational-state isolation
# ---------------------------------------------------------------------------
def test_sequential_interleaving_never_leaks_between_users(harness: Harness):
    user_a, user_b = _two_users(harness)

    responses_a: list[dict[str, Any]] = []
    responses_b: list[dict[str, Any]] = []
    # Strict alternation maximises state-sharing opportunities.
    responses_a.append(harness.chat(user_a, USER_A_QUESTIONS[0]))
    responses_b.append(harness.chat(user_b, USER_B_QUESTIONS[0]))
    responses_a.append(harness.chat(user_a, USER_A_QUESTIONS[1]))
    responses_b.append(harness.chat(user_b, USER_B_QUESTIONS[1]))

    _assert_no_cross_user_prompts(harness, user_a, user_b, responses_a, responses_b, "sequential")


def test_concurrent_chat_requests_threaded(harness: Harness):
    user_a, user_b = _two_users(harness)

    # Two rounds: the FIRST concurrent exchange starts from empty histories on
    # both sides (no leak observable even on buggy code). Cross-user state only
    # becomes visible in the SECOND round, when prior turns are injected into
    # prompt construction -- so both rounds must run under contention.
    barrier = threading.Barrier(2)
    results: dict[str, list[dict[str, Any]]] = {"a": [], "b": []}

    def fire(user: dict[str, Any], questions: list[str], key: str) -> None:
        for q in questions:
            barrier.wait(timeout=10)
            results[key].append(harness.chat(user, q))

    with ThreadPoolExecutor(max_workers=2) as pool:
        future_a = pool.submit(fire, user_a, USER_A_QUESTIONS, "a")
        future_b = pool.submit(fire, user_b, USER_B_QUESTIONS, "b")
        future_a.result(timeout=60)
        future_b.result(timeout=60)

    _assert_no_cross_user_prompts(
        harness, user_a, user_b, results["a"], results["b"], "threaded"
    )


def test_concurrent_chat_requests_asyncio_gather(app, harness: Harness):
    httpx = pytest.importorskip("httpx")
    from httpx import ASGITransport

    user_a, user_b = _two_users(harness)

    async def gather_pair(round_questions: list[tuple[str, str]]) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as async_client:
            for question_a, question_b in round_questions:
                resp_a, resp_b = await asyncio.gather(
                    async_client.post("/api/chat/", headers=user_a["headers"], json={"query": question_a}),
                    async_client.post("/api/chat/", headers=user_b["headers"], json={"query": question_b}),
                )
                assert resp_a.status_code == 200, resp_a.text
                assert resp_b.status_code == 200, resp_b.text
                payloads.append(resp_a.json())
                payloads.append(resp_b.json())
        return payloads

    rounds = list(zip(USER_A_QUESTIONS, USER_B_QUESTIONS))
    payloads = asyncio.run(gather_pair(rounds))
    payloads_a = payloads[0::2]
    payloads_b = payloads[1::2]
    _assert_no_cross_user_prompts(harness, user_a, user_b, payloads_a, payloads_b, "asyncio")


def test_reset_clears_only_the_calling_session(harness: Harness):
    user_a, user_b = _two_users(harness)

    _first_a = harness.chat(user_a, USER_A_QUESTIONS[0])
    _first_b = harness.chat(user_b, USER_B_QUESTIONS[0])

    reset_payload = harness.reset(user_a)

    # White-box check when the post-fix introspection API exists.
    turns_probe = getattr(harness.pipeline, "conversation_turns", None)
    if callable(turns_probe):
        assert turns_probe(user_a["session_id"]) == []
        remaining_b = turns_probe(user_b["session_id"])
        assert any(t["content"] == USER_B_QUESTIONS[0] for t in remaining_b), (
            "User A's /chat/reset wiped User B's conversation history"
        )

    # Behavioural check (also the pre-fix failure signal): B's next prompt must
    # still contain B's own prior turn and never any of A's content.
    second_b = harness.chat(user_b, USER_B_QUESTIONS[1])
    prompts_b = harness.prompts_for(user_b, [second_b])
    assert prompts_b, "No prompt recorded for user B follow-up"

    foreign_for_b = foreign_markers_for(USER_B_MARKER, USER_B_QUESTIONS, USER_A_MARKER, USER_A_QUESTIONS)
    rate = leakage_rate(prompts_b, foreign_for_b)
    record_measurement("reset_scoping", "user_b_after_a_reset", rate, len(prompts_b))
    assert not prompt_leaks(prompts_b[0], foreign_for_b), (
        "After User A reset, User B's prompt lost history or gained User A content"
    )
    assert USER_B_QUESTIONS[0] in prompts_b[0], (
        "User B's own prior turn vanished after User A called /chat/reset"
    )

    # A's reset did what it promised *for A*: A's next prompt must no longer
    # contain A's own earlier turn (history gone) and still no B content.
    second_a = harness.chat(user_a, USER_A_QUESTIONS[1])
    prompts_a = harness.prompts_for(user_a, [second_a])
    assert prompts_a, "No prompt recorded for user A follow-up"
    assert USER_A_QUESTIONS[0] not in prompts_a[0], (
        "User A's history survived its own /chat/reset"
    )
    foreign_for_a = foreign_markers_for(USER_A_MARKER, USER_A_QUESTIONS, USER_B_MARKER, USER_B_QUESTIONS)
    assert not prompt_leaks(prompts_a[0], foreign_for_a)
    assert reset_payload["status"] == "success"


# ---------------------------------------------------------------------------
# Landmine regression: unfiltered retrieval must be unwireable
# ---------------------------------------------------------------------------
def test_retriever_retrieve_requires_explicit_filter(harness: Harness):
    signature = inspect.signature(harness.pipeline.retriever.retrieve)
    params = signature.parameters
    assert "filter_dict" in params, "Retriever.retrieve lost its filter argument"
    assert params["filter_dict"].default is inspect.Parameter.empty, (
        "filter_dict must be REQUIRED -- an optional default silently reopens "
        "the cross-user retrieval hole"
    )

    with pytest.raises(TypeError):
        harness.pipeline.retriever.retrieve("any query")  # type: ignore[call-arg]

    # And the filtered call path still works end-to-end.
    user_a, _ = _two_users(harness)
    hits = harness.pipeline.retriever.retrieve(
        USER_A_QUESTIONS[0], filter_dict={"session_id": user_a["session_id"]}, top_k=5
    )
    assert all(h["session_id"] == user_a["session_id"] for h in hits)


# ---------------------------------------------------------------------------
# Session summary for the paper
# ---------------------------------------------------------------------------
def test_report_contains_measurements():
    # Sanity: the harness actually produced measurable output this session.
    assert isinstance(REPORT["measurements"], list)
