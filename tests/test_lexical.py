from core.lexical import BM25Index, reciprocal_rank_fusion, tokenize


def test_tokenize_keeps_identifiers_and_their_parts():
    tokens = tokenize("Invoice No: INV-2023-8285 Slip SS/2023/02/EMP-0089")
    assert "inv-2023-8285" in tokens and "8285" in tokens
    assert "ss/2023/02/emp-0089" in tokens and "emp" in tokens


def test_bm25_ranks_the_document_with_the_exact_identifier_first():
    docs = [
        "Invoice No: INV-2023-8285 From: Chemco Formulations Ltd.",
        "Invoice No: INV-2023-8286 From: EcoBox Sustainable Packs",
        "Debit Note against Invoice INV-2022-1481",
    ]
    hits = BM25Index(docs).search("Which vendor issued invoice INV-2023-8285?", top_k=3)
    assert hits[0][0] == 0


def test_bm25_ignores_unknown_terms():
    assert BM25Index(["alpha beta"]).search("gamma") == []


def test_reciprocal_rank_fusion_rewards_agreement():
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["b", "a", "d"]])
    assert fused[:2] == ["a", "b"] or fused[:2] == ["b", "a"]
    assert set(fused) == {"a", "b", "c", "d"}
    assert reciprocal_rank_fusion([["x", "y"], ["y"]])[0] == "y"
