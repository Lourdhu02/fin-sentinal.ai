def reciprocal_rank_fusion(*rankings, limit=40, rank_constant=60):
    """Combine rankings without mixing incomparable vector/BM25 score scales."""
    scores = {}
    items = {}
    for ranking in rankings:
        seen = set()
        for rank, item in enumerate(ranking, 1):
            key = item["chunk_id"]
            if key in seen:
                continue
            seen.add(key)
            items[key] = item
            scores[key] = scores.get(key, 0.0) + 1 / (rank_constant + rank)
    keys = sorted(scores, key=lambda key: (-scores[key], key))[:limit]
    return [{**items[key], "fusion_score": scores[key]} for key in keys]
