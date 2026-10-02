"""Retrieval metrics for the FinSentinelAI benchmark (pure Python, unit-tested)."""

from __future__ import annotations

import re
from typing import Iterable, Sequence


def ranked_files(results: Sequence[dict]) -> list[str]:
    """Collapse chunk-level results to a ranked list of distinct source files."""
    seen: list[str] = []
    for item in results:
        name = str(item.get("file_name", ""))
        if name and name not in seen:
            seen.append(name)
    return seen


def hit_at_k(files: Sequence[str], gold: str, k: int) -> bool:
    return gold in files[:k]


def reciprocal_rank(files: Sequence[str], gold: str) -> float:
    for rank, name in enumerate(files, start=1):
        if name == gold:
            return 1.0 / rank
    return 0.0


def answer_match(response: str, answer: str) -> bool:
    """True if the gold answer appears in the response, ignoring case and spacing."""
    norm = lambda s: re.sub(r"\s+", " ", s).strip().lower()  # noqa: E731
    return norm(answer) in norm(response)


def mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def percentile(values: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile, q in [0, 100]."""
    if not values:
        return 0.0
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q / 100.0
    lo, hi = int(pos), min(int(pos) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)
