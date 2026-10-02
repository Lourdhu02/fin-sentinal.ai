"""BM25 keyword index for exact-identifier lookups.

Dense embeddings blur identifiers such as invoice numbers (INV-2023-8285),
GST ARNs or PO numbers into near-identical vectors, so a question that names
one rarely retrieves the right document. BM25 matches them exactly. The
tokenizer keeps hyphenated or slashed identifiers whole and also indexes
their parts.
"""

from __future__ import annotations

import math
import re
from collections import Counter

_TOKEN = re.compile(r"[a-z0-9]+(?:[-/][a-z0-9]+)*")


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for token in _TOKEN.findall(text.lower()):
        tokens.append(token)
        if "-" in token or "/" in token:
            tokens.extend(part for part in re.split(r"[-/]", token) if part)
    return tokens


class BM25Index:
    def __init__(self, texts: list[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.doc_tf = [Counter(tokenize(t)) for t in texts]
        self.doc_len = [sum(tf.values()) for tf in self.doc_tf]
        self.avg_len = (sum(self.doc_len) / len(self.doc_len)) if self.doc_len else 0.0
        df: Counter = Counter()
        for tf in self.doc_tf:
            df.update(tf.keys())
        n = len(texts)
        self.idf = {term: math.log(1 + (n - d + 0.5) / (d + 0.5)) for term, d in df.items()}
        self.postings: dict[str, list[int]] = {}
        for i, tf in enumerate(self.doc_tf):
            for term in tf:
                self.postings.setdefault(term, []).append(i)

    def search(self, query: str, top_k: int = 20) -> list[tuple[int, float]]:
        scores: dict[int, float] = {}
        for term in set(tokenize(query)):
            idf = self.idf.get(term)
            if idf is None:
                continue
            for i in self.postings[term]:
                tf = self.doc_tf[i][term]
                norm = self.k1 * (1 - self.b + self.b * self.doc_len[i] / (self.avg_len or 1.0))
                scores[i] = scores.get(i, 0.0) + idf * tf * (self.k1 + 1) / (tf + norm)
        return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top_k]


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = 60) -> list[str]:
    """Fuse ranked id lists (Cormack et al., 2009): score(d) = sum 1 / (k + rank)."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, key in enumerate(ranking, start=1):
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda key: scores[key], reverse=True)
