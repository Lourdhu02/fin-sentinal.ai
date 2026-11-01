import pytest

from core.evaluation import retrieval_metrics


def test_metrics_use_rank_and_deduplicate():
    result = retrieval_metrics(["a", "b"], ["x", "a", "a"], k=5)
    assert result["recall"] == 0.5
    assert result["mrr"] == 0.5
    assert 0 < result["ndcg"] < 1


def test_perfect_retrieval():
    assert retrieval_metrics(["a"], ["a"]) == {"recall": 1, "mrr": 1, "ndcg": 1}
    with pytest.raises(ValueError):
        retrieval_metrics([], [])


def test_duplicate_results_consume_rank_slots():
    assert retrieval_metrics(["a"], ["x", "x", "a"], k=2)["recall"] == 0
    assert retrieval_metrics(["a"], ["x", "x", "a"], k=3)["mrr"] == pytest.approx(1 / 3)
