from __future__ import annotations

import os
import warnings

# Suppress noisy transformers/torch warnings
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
warnings.filterwarnings("ignore", message=".*__path__.*")
warnings.filterwarnings("ignore", category=FutureWarning)

import numpy as np

from config import get_settings


class LocalEmbedder:
    def __init__(self, model_name: str | None = None) -> None:
        self.settings = get_settings()
        self.model_name = model_name or self.settings.embedding_model
        self.dimension = 384
        self._model = None
        self._load_model()

    def _load_model(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(
                self.model_name, device="cpu", local_files_only=self.settings.offline
            )
            if hasattr(self._model, "get_embedding_dimension"):
                detected_dimension = self._model.get_embedding_dimension()
            else:
                detected_dimension = self._model.get_sentence_embedding_dimension()
            if detected_dimension:
                self.dimension = int(detected_dimension)
        except Exception as exc:
            raise RuntimeError(
                "Embedding model unavailable. Provision the configured model before offline startup."
            ) from exc

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)
        if self._model is not None:
            embeddings = self._model.encode(
                texts,
                batch_size=32,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            return np.asarray(embeddings, dtype=np.float32)
        raise RuntimeError("Embedding model is not loaded")

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed_texts([text])[0]


