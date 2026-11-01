from core.benchmarks.resources import Resources, percentile


def test_resource_scope_and_optional_python_tracing():
    with Resources(trace_python_heap=True) as measured:
        data = bytearray(10000)
        assert len(data) == 10000
    assert measured.result["python_heap_peak_bytes"] >= 10000
    assert measured.result["wall_seconds"] >= 0
    assert "GPU peak is not measured" in measured.result["scope"]


def test_percentiles_have_explicit_empty_and_nearest_rank_behavior():
    assert percentile([], .95) is None
    assert percentile([1, 2, 3, 4], .5) == 2
    assert percentile([1, 2, 3, 4], .95) == 4
