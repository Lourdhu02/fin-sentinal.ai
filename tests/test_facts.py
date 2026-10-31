from core.facts import extract_facts
from core.ocr_parser import ParsedPage


def test_exact_observations_include_source_region():
    text = "Currency INR\nSubtotal: 1,23,456.78\nTotal Tax: 12.34\nGrand Total: 1,23,469.12"
    facts = extract_facts([ParsedPage(2, text, "text")])
    observed = facts["fields"]["total"][0]
    assert observed["amount"] == "123469.12"
    assert observed["page"] == 2
    assert text[observed["start_char"]:observed["end_char"]] == observed["raw"]
    assert facts["validated"] is False


def test_missing_currency_disables_aggregation():
    facts = extract_facts([ParsedPage(1, "Grand Total: 12.30", "text")])
    assert facts["currency"] is None
    assert facts["issues"]
