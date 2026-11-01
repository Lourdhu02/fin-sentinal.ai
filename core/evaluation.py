"""Deterministic retrieval metrics; inputs are externally reviewed judgments."""
import argparse
import json
import math
from pathlib import Path


def retrieval_metrics(expected, retrieved, k=5):
    relevant = set(expected)
    if not relevant or k <= 0:
        raise ValueError("Expected evidence and positive k are required")
    # Repeated predictions must never improve a score.
    ranked = retrieved[:k]
    seen = set()
    hits = []
    for key in ranked:
        hits.append(int(key in relevant and key not in seen))
        seen.add(key)
    recall = sum(hits) / len(relevant)
    reciprocal_rank = next((1 / (i + 1) for i, hit in enumerate(hits) if hit), 0.0)
    dcg = sum(hit / math.log2(i + 2) for i, hit in enumerate(hits))
    ideal = sum(1 / math.log2(i + 2) for i in range(min(k, len(relevant))))
    return {"recall": recall, "mrr": reciprocal_rank, "ndcg": dcg / ideal}


def main():
    parser = argparse.ArgumentParser(description="Score JSONL retrieval judgments")
    parser.add_argument("judgments", type=Path)
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()
    scores = []
    with args.judgments.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                record = json.loads(line)
                scores.append(retrieval_metrics(record["expected"], record["retrieved"], args.k))
    if not scores:
        parser.error("No judgments found")
    print(json.dumps({"queries": len(scores), "k": args.k,
                      "metrics": {key: sum(s[key] for s in scores) / len(scores) for key in scores[0]}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
