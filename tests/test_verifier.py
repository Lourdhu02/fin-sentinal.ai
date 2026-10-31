from core.finance import Money, reconcile


def test_financial_reconciliation_detects_mismatch():
    assert reconcile(Money("100.10", "INR"), Money("18.02", "INR"), Money("118.12", "INR"))
    assert not reconcile(Money("100.10", "INR"), Money("18.02", "INR"), Money("118.13", "INR"))
