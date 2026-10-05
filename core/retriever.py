from __future__ import annotations

import re
from typing import Any

from core.embedder import LocalEmbedder
from database.vector_store import ChromaDBVectorStore


class Retriever:
    def __init__(self, embedder: LocalEmbedder, vector_store: ChromaDBVectorStore) -> None:
        self.embedder = embedder
        self.vector_store = vector_store
        self._reranker = None
        self._load_reranker()

    def _load_reranker(self) -> None:
        try:
            from sentence_transformers import CrossEncoder
            self._reranker = CrossEncoder(
                "cross-encoder/ms-marco-MiniLM-L-6-v2",
                device="cpu",
            )
        except Exception:
            self._reranker = None

    def retrieve(self, query: str, filter_dict: dict[str, Any], top_k: int = 20) -> list[dict]:
        """Retrieve chunks from the vector store.

        ``filter_dict`` is intentionally REQUIRED (no default): calling this
        without an explicit isolation filter (e.g. ``{"session_id": ...}``)
        would silently return every user's data. Do not "simplify" this
        signature back to an optional filter.
        """
        query_embedding = self.embedder.embed_query(query)
        return self.vector_store.search(query_embedding, top_k=top_k, filter_dict=filter_dict)

    def rerank(self, query: str, results: list[dict], top_n: int = 8) -> list[dict]:
        if not results:
            return results
        if self._reranker is None:
            return results[:top_n]
        pairs = [(query, str(r.get("text", ""))) for r in results]
        scores = self._reranker.predict(pairs)
        ranked = sorted(zip(scores, results), key=lambda x: x[0], reverse=True)
        return [r for _, r in ranked[:top_n]]

    def analyze_query(self, query: str) -> dict[str, Any]:
        normalized = re.sub(r"\s+", " ", query.strip().lower())

        if any(t in normalized for t in ("total spend", "total amount", "sum", "how much did we spend", "total invoice")):
            return {"kind": "total", "target": None, "query": normalized}

        if any(t in normalized for t in ("vendor summary", "vendor breakdown", "spend by vendor", "top vendor")):
            return {"kind": "vendor_summary", "target": None, "query": normalized}

        if "how many" in normalized or normalized.startswith("count"):
            return {
                "kind": "count",
                "target": self._extract_count_target(normalized),
                "query": normalized,
            }

        return {"kind": "llm", "target": None, "query": normalized}

    def _extract_count_target(self, query: str) -> str | None:
        how_many = re.search(
            r"\bhow many\s+([a-z][a-z0-9 _-]*?)(?:\s+(?:were|was|are|is|have|has|did|do|purchased|bought|ordered|found|in)\b|$)",
            query,
        )
        count_m = re.search(
            r"\bcount\s+([a-z][a-z0-9 _-]*?)(?:\s+(?:were|was|are|is|have|has|purchased|bought|ordered|found|in)\b|$)",
            query,
        )
        candidate = how_many.group(1) if how_many else count_m.group(1) if count_m else None
        if not candidate:
            return None
        cleaned = re.sub(r"\b(total|all|items|item|purchases|purchase)\b", "", candidate).strip(" ?.")
        cleaned = re.sub(r"\s+", " ", cleaned)
        if not cleaned:
            return None
        if cleaned.endswith("s") and len(cleaned) > 3:
            cleaned = cleaned[:-1]
        return cleaned
