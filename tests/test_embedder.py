import sys
from types import SimpleNamespace

import pytest

from core.embedder import LocalEmbedder


def test_missing_embedding_model_fails_explicitly(monkeypatch):
    def missing(*args, **kwargs):
        assert kwargs["local_files_only"] is True
        raise OSError("missing")

    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=missing))
    with pytest.raises(RuntimeError, match="Provision"):
        LocalEmbedder()
