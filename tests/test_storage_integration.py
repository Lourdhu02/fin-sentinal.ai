from pathlib import Path

import numpy as np
import pytest


def test_real_chroma_upsert_filter_and_delete(tmp_path):
    pytest.importorskip("chromadb")
    from database.vector_store import ChromaDBVectorStore

    store = ChromaDBVectorStore(tmp_path / "vectors")
    metadata = [{"chunk_id": "a", "user_id": 1, "session_id": "user_1_default", "text": "alice"},
                {"chunk_id": "b", "user_id": 2, "session_id": "user_2_default", "text": "bob"}]
    embeddings = np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float32)
    store.add(embeddings, metadata)
    store.add(embeddings, metadata)
    assert store.collection.count() == 2
    result = store.search(embeddings[0], filter_dict={"user_id": 1, "session_id": "user_1_default"})
    assert [item["chunk_id"] for item in result] == ["a"]
    store.delete_by_filter({"user_id": 1, "session_id": "user_1_default"})
    assert store.search(embeddings[0], filter_dict={"user_id": 1}) == []
    assert store.collection.count() == 1


@pytest.mark.parametrize("category", ["invoices", "salary_slips", "bank_statements", "gst_returns", "credit_debit_notes", "purchase_orders"])
def test_native_pdf_corpus_smoke(category):
    pytest.importorskip("pdfplumber")
    from core.ocr_parser import OCRParser

    root = Path(__file__).resolve().parents[1] / "test-data" / "sugar_dataset" / category
    source = next(iter(sorted(root.glob("*.pdf"))))
    pages = OCRParser().parse_pdf_pages(source)
    assert pages
    assert all(page.page > 0 and page.text.strip() for page in pages)
