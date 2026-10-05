import os
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    with TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        monkeypatch.setenv("FINSENTINEL_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("FINSENTINEL_ENV", "test")
        yield tmp_path

class FakeEmbedder:
    def embed_texts(self, texts):
        import hashlib
        # Return deterministic 384-d vectors based on hash of text
        res = []
        for text in texts:
            h = int(hashlib.sha256(text.encode()).hexdigest(), 16)
            vec = [(h % (i + 1)) / (i + 1) for i in range(384)]
            res.append(vec)
        return res
    def embed_query(self, query):
        return self.embed_texts([query])[0]

class FakeReranker:
    def rerank(self, query, results, top_n=10):
        # identity pass-through
        return results[:top_n]

class FakeLLM:
    def generate(self, question, results, summaries, conversation_history):
        return f"Fake answer to: {question}"

@pytest.fixture
def fake_embedder(monkeypatch):
    embedder = FakeEmbedder()
    monkeypatch.setattr("core.embedder.LocalEmbedder", lambda: embedder)
    return embedder

@pytest.fixture
def fake_pipeline(fake_embedder, monkeypatch):
    from core.pipeline import FinSentinelPipeline
    monkeypatch.setattr("core.retriever.Retriever.rerank", FakeReranker().rerank)
    pipeline = FinSentinelPipeline()
    pipeline.llm_engine = FakeLLM()
    pipeline.embedder = fake_embedder
    return pipeline
