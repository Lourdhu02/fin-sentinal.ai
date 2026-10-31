import pytest

from core.chunking import chunk_text


def test_chunk_offsets_preserve_every_character():
    text = ("Invoice paragraph.\n\n" * 100).strip()
    chunks = chunk_text(text, size=100, overlap=10)
    covered = set()
    for chunk in chunks:
        assert chunk["text"] == text[chunk["start_char"]:chunk["end_char"]]
        assert len(chunk["text"]) <= 100
        covered.update(range(chunk["start_char"], chunk["end_char"]))
    assert len(covered) == len(text)


def test_invalid_chunk_parameters_rejected():
    with pytest.raises(ValueError):
        chunk_text("data", size=10, overlap=10)
