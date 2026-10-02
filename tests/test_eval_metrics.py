from eval.metrics import answer_match, hit_at_k, percentile, ranked_files, reciprocal_rank


def test_ranked_files_dedupes_chunks_in_order():
    results = [{"file_name": "a.pdf"}, {"file_name": "b.pdf"}, {"file_name": "a.pdf"}, {"file_name": "c.pdf"}]
    assert ranked_files(results) == ["a.pdf", "b.pdf", "c.pdf"]


def test_hit_and_reciprocal_rank():
    files = ["a.pdf", "b.pdf", "c.pdf"]
    assert hit_at_k(files, "b.pdf", 2) and not hit_at_k(files, "c.pdf", 2)
    assert reciprocal_rank(files, "c.pdf") == 1 / 3
    assert reciprocal_rank(files, "z.pdf") == 0.0


def test_answer_match_ignores_case_and_spacing():
    assert answer_match("The vendor is  CHEMCO Formulations Ltd.", "Chemco Formulations Ltd.")
    assert not answer_match("Net 30", "Net 45")


def test_percentile_interpolates():
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert percentile([5], 95) == 5
    assert percentile([], 50) == 0.0
