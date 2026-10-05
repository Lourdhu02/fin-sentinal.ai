import pytest
from core.extractor import detect_kind
from core.verifier import InvoiceVerifier
from core.anomaly import AnomalyDetector
from models.invoice import Invoice
from models.anomaly import AnomalyScore

def test_classification_accuracy():
    # Tie-breaker path neutral
    assert detect_kind("this is a salary slip", "doc_0001.pdf") == "salary_slip"
    assert detect_kind("invoice number 123", "doc_0002.pdf") == "invoice"
    assert detect_kind("bank statement for user", "doc_0003.pdf") == "bank_statement"
    assert detect_kind("purchase order 555", "doc_0004.pdf") == "purchase_order"
    assert detect_kind("credit note issued", "doc_0005.pdf") == "credit_debit_note"

def test_verifier_catches_arithmetic_errors(test_db):
    verifier = InvoiceVerifier()
    # Good invoice
    inv = Invoice(
        invoice_number="INV-01", vendor_name="Vendor A", document_path="doc.pdf",
        subtotal=100.0, tax=10.0, total=110.0, currency="USD", content="", content_hash="hash1", created_by=1, metadata={}
    )
    res = verifier.verify_invoice(inv, test_db)
    assert res.is_valid is True
    
    # Bad invoice
    inv_bad = Invoice(
        invoice_number="INV-02", vendor_name="Vendor A", document_path="doc.pdf",
        subtotal=100.0, tax=10.0, total=120.0, currency="USD", content="", content_hash="hash2", created_by=1, metadata={}
    )
    res_bad = verifier.verify_invoice(inv_bad, test_db)
    assert res_bad.is_valid is False
    assert "Arithmetic mismatch" in res_bad.issues[0]

def test_detector_flags_outliers():
    detector = AnomalyDetector()
    # Normal
    res = detector.score(105.0, [100.0, 102.0, 98.0, 101.0, 105.0, 99.0, 95.0, 103.0, 100.0])
    assert res.is_anomaly is False
    
    # Outlier
    res_outlier = detector.score(10000.0, [100.0, 102.0, 98.0, 101.0, 105.0, 99.0, 95.0, 103.0, 100.0])
    assert res_outlier.is_anomaly is True

def test_sql_answers(fake_pipeline, test_db):
    # Route total
    route = {"kind": "total", "user_id": 1}
    ans = fake_pipeline._handle_structured_query(route, "What is the total spend?", 1)
    assert "Total spend across 0 documents" in ans
    
    # Add an invoice
    inv = Invoice(
        invoice_number="INV-01", vendor_name="Vendor A", document_path="doc.pdf",
        subtotal=100.0, tax=10.0, total=110.0, currency="USD", content="", content_hash="hash1", created_by=1, metadata={}
    )
    test_db.create_invoice(inv)
    
    ans2 = fake_pipeline._handle_structured_query(route, "What is the total spend?", 1)
    assert "Total spend across 1 documents" in ans2
    assert "110" in ans2
