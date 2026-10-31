from core.citations import verify_citations


def test_citations_must_resolve_to_current_evidence():
    a, b = "a" * 64, "b" * 64
    assert verify_citations(f"Observed amount [source:{a}]", [{"chunk_id": a}])
    assert not verify_citations(f"Wrong [source:{b}]", [{"chunk_id": a}])
    assert not verify_citations("Unsupported answer", [{"chunk_id": a}])
