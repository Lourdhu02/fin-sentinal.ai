from core.fusion import reciprocal_rank_fusion


def test_shared_evidence_promoted_without_duplicate_boost():
    a, b, c = [{"chunk_id": key} for key in "abc"]
    result = reciprocal_rank_fusion([a, b, b], [c, b])
    assert [r["chunk_id"] for r in result] == ["b", "a", "c"]
    assert len(result) == 3
