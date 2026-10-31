from contextlib import nullcontext
from types import SimpleNamespace
import sys

import pytest

from core.ocr_parser import OCRParser


def test_pdf_page_provenance(monkeypatch):
    pdf = SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda **kw: "Invoice 123")])
    monkeypatch.setitem(sys.modules, "pdfplumber", SimpleNamespace(open=lambda _: nullcontext(pdf)))
    pages = OCRParser().parse_pdf_pages("document.pdf")
    assert (pages[0].page, pages[0].parser, pages[0].text) == (1, "pdfplumber", "Invoice 123")


def test_page_limit_before_extraction(monkeypatch):
    pdf = SimpleNamespace(pages=[None] * 201)
    monkeypatch.setitem(sys.modules, "pdfplumber", SimpleNamespace(open=lambda _: nullcontext(pdf)))
    with pytest.raises(ValueError, match="page limit"):
        OCRParser().parse_pdf_pages("document.pdf")
