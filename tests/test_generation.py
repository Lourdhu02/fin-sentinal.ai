import pytest

from core.llm_engine import LlamaCppEngine, OllamaEngine, create_generator


@pytest.mark.parametrize("engine", [OllamaEngine, LlamaCppEngine])
def test_local_provider_contract(engine, monkeypatch):
    def post(endpoint, payload):
        assert payload["stream"] is False
        return {"response": "cited answer", "choices": [{"message": {"content": "cited answer"}}]}

    monkeypatch.setattr("core.llm_engine.post_json", post)
    item = {"chunk_id": "a" * 64, "file_name": "a.txt", "page": 1, "text": "facts"}
    assert engine().generate("question", [item], []) == "cited answer"


def test_no_evidence_never_calls_model(monkeypatch):
    monkeypatch.setattr("core.llm_engine.post_json", lambda *args: pytest.fail("Network called"))
    assert "enough evidence" in OllamaEngine().generate("question", [], [])


def test_unsupported_backend_rejected(monkeypatch):
    monkeypatch.setenv("FINSENTINEL_INFERENCE", "remote")
    with pytest.raises(ValueError):
        create_generator()
