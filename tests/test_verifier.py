"""Unit tests for InvoiceVerifier: total verification and duplicate detection."""

from __future__ import annotations

import hashlib

from models.invoice import Invoice
from core.verifier import InvoiceVerifier


def _invoice(
    subtotal: float = 100.0,
    tax: float = 5.0,
    total: float = 105.0,
    content: str = "Invoice body text",
    invoice_id: int | None = None,
    content_hash: str | None = None,
) -> Invoice:
    return Invoice(
        id=invoice_id,
        invoice_number="INV-001",
        vendor_name="Acme Corp",
        document_path="/docs/inv-001.pdf",
        subtotal=subtotal,
        tax=tax,
        total=total,
        currency="INR",
        content=content,
        content_hash=content_hash if content_hash is not None else hashlib.sha256(content.encode("utf-8")).hexdigest(),
    )


class StubDB:
    """Minimal db_manager stand-in exposing only get_invoice_by_hash."""

    def __init__(self, invoice: Invoice | None):
        self._invoice = invoice
        self.requested_hashes: list[str] = []

    def get_invoice_by_hash(self, content_hash: str) -> Invoice | None:
        self.requested_hashes.append(content_hash)
        return self._invoice


# ---------------------------------------------------------------------------
# Content hashing
# ---------------------------------------------------------------------------
def test_calculate_hash_is_sha256_of_utf8_content():
    verifier = InvoiceVerifier()
    assert verifier.calculate_hash("hello") == hashlib.sha256(b"hello").hexdigest()


def test_calculate_hash_is_deterministic_and_sensitive():
    verifier = InvoiceVerifier()
    assert verifier.calculate_hash("abc") == verifier.calculate_hash("abc")
    assert verifier.calculate_hash("abc") != verifier.calculate_hash("abd")


# ---------------------------------------------------------------------------
# Total verification
# ---------------------------------------------------------------------------
def test_matching_totals_are_valid():
    result = InvoiceVerifier().verify_invoice(_invoice(subtotal=250.0, tax=12.5, total=262.5))

    assert result.totals_valid is True
    assert result.computed_total == 262.5
    assert result.issues == []


def test_mismatched_totals_flag_an_issue():
    result = InvoiceVerifier().verify_invoice(_invoice(subtotal=100.0, tax=5.0, total=999.0))

    assert result.totals_valid is False
    assert any("Total mismatch" in issue for issue in result.issues)
    assert result.computed_total == 105.0


def test_tolerance_boundary_at_five_cents():
    verifier = InvoiceVerifier()
    within = verifier.verify_invoice(_invoice(subtotal=100.0, tax=5.0, total=105.05))
    outside = verifier.verify_invoice(_invoice(subtotal=100.0, tax=5.0, total=105.06))

    assert within.totals_valid is True   # |diff| == 0.05 is tolerated
    assert outside.totals_valid is False


def test_tax_rate_computation():
    verifier = InvoiceVerifier()
    assert verifier.verify_invoice(_invoice(subtotal=200.0, tax=30.0)).tax_rate == 0.15
    assert verifier.verify_invoice(_invoice(subtotal=0.0, tax=10.0)).tax_rate == 0.0


# ---------------------------------------------------------------------------
# Duplicate detection via content hash
# ---------------------------------------------------------------------------
def test_duplicate_detected_against_existing_hash():
    verifier = InvoiceVerifier()
    original = _invoice(invoice_id=42)
    duplicate = _invoice(invoice_id=43)  # identical content -> identical hash
    stub = StubDB(original)

    result = verifier.verify_invoice(duplicate, db_manager=stub)

    assert stub.requested_hashes == [duplicate.content_hash]
    assert result.duplicate is True
    assert result.duplicate_invoice_id == 42
    assert any("Duplicate content" in issue for issue in result.issues)


def test_same_invoice_id_is_not_a_duplicate_of_itself():
    verifier = InvoiceVerifier()
    invoice = _invoice(invoice_id=7)
    stub = StubDB(invoice)  # hash lookup returns the SAME invoice

    result = verifier.verify_invoice(invoice, db_manager=stub)

    assert result.duplicate is False
    assert result.duplicate_invoice_id is None


def test_no_db_manager_means_no_duplicate_check():
    result = InvoiceVerifier().verify_invoice(_invoice(), db_manager=None)

    assert result.duplicate is False
    assert result.issues == []


def test_content_hash_falls_back_to_computed_when_missing():
    invoice = _invoice(content="fallback body", content_hash="")

    result = InvoiceVerifier().verify_invoice(invoice)

    assert result.content_hash == hashlib.sha256(b"fallback body").hexdigest()
