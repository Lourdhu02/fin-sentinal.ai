"""Conservative source observations, kept separate from legacy float extraction."""
import re

from core.finance import decimal_amount


LABELS = {"subtotal": r"sub\s*total", "tax": r"total\s+tax", "total": r"grand\s+total|total\s+payable|net\s+pay"}


def extract_facts(pages):
    fields = {}
    currencies = set()
    issues = []
    for page in pages:
        for currency in re.findall(r"\b(?:INR|USD|EUR|GBP)\b", page.text):
            currencies.add(currency)
        if "₹" in page.text:
            currencies.add("INR")
        for name, label in LABELS.items():
            for match in re.finditer(rf"(?im)^\s*(?:{label})\s*[:=]?\s*((?:INR|USD|EUR|GBP|₹|\$)?\s*\(?-?[\d,]+(?:\.\d+)?\)?)\s*$", page.text):
                raw = match.group(1).strip()
                try:
                    value = str(decimal_amount(raw))
                except ValueError:
                    issues.append(f"Invalid {name} amount on page {page.page}")
                    continue
                fields.setdefault(name, []).append({"raw": raw, "amount": value, "page": page.page,
                                                    "start_char": match.start(1), "end_char": match.end(1)})
    if len(currencies) != 1:
        issues.append("Currency missing or ambiguous; aggregation disabled")
    return {"version": "observations-v1", "currency": next(iter(currencies)) if len(currencies) == 1 else None,
            "fields": fields, "issues": issues, "validated": False}
