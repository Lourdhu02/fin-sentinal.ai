from __future__ import annotations

import re
from typing import Any

from core.embedder import LocalEmbedder
from core.lexical import BM25Index, reciprocal_rank_fusion
from database.vector_store import ChromaDBVectorStore


class Retriever:
    def __init__(self, embedder: LocalEmbedder, vector_store: ChromaDBVectorStore) -> None:
        self.embedder = embedder
        self.vector_store = vector_store
        self._reranker = None
        self._bm25_cache: dict[tuple, tuple[BM25Index, list[dict]]] = {}
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

    def retrieve(self, query: str, top_k: int = 20) -> list[dict]:
        query_embedding = self.embedder.embed_query(query)
        return self.vector_store.search(query_embedding, top_k=top_k)

    def keyword_search(self, query: str, top_k: int = 20, filter_dict: dict | None = None) -> list[dict]:
        key = (tuple(sorted((filter_dict or {}).items())), self.vector_store.collection.count())
        if key not in self._bm25_cache:
            docs = self.vector_store.documents(filter_dict)
            self._bm25_cache = {key: (BM25Index([str(d.get("text", "")) for d in docs]), docs)}
        index, docs = self._bm25_cache[key]
        return [{**docs[i], "bm25": score} for i, score in index.search(query, top_k)]

    def hybrid_search(self, query: str, top_k: int = 20, filter_dict: dict | None = None) -> list[dict]:
        """Dense and BM25 candidates fused with reciprocal-rank fusion."""
        dense = self.vector_store.search(self.embedder.embed_query(query), top_k=top_k, filter_dict=filter_dict)
        lexical = self.keyword_search(query, top_k=top_k, filter_dict=filter_dict)
        by_id = {r["vector_id"]: r for r in dense + lexical}
        fused = reciprocal_rank_fusion([[r["vector_id"] for r in dense], [r["vector_id"] for r in lexical]])
        return [by_id[i] for i in fused[:top_k]]

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
