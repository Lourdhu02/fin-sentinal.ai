from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from models.document import DocumentKind, ExtractedDocument


def _clean(text: str) -> str:
    text = text.replace("\x00", " ").replace("\r", "\n")
    text = re.sub(r"[^\S\n]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[â– â–¡â–ªâ–¸â—â—†]", "â‚¹", text)
    return text.strip()


def _amount(value: str | None) -> float:
    if not value:
        return 0.0
    cleaned = re.sub(r"[^\d.,\-]", "", str(value)).strip()
    if not cleaned:
        return 0.0
    if cleaned.count(",") > 0 and cleaned.count(".") == 0:
        cleaned = cleaned.replace(",", ".")
    elif cleaned.count(",") > 0 and cleaned.count(".") > 0:
        cleaned = cleaned.replace(",", "")
    try:
        return round(float(cleaned), 2)
    except ValueError:
        return 0.0


def _find(pattern: str, text: str, group: int = 1, flags: int = re.IGNORECASE) -> str:
    m = re.search(pattern, text, flags)
    return m.group(group).strip() if m else ""


def _find_amount(labels: list[str], text: str) -> float:
    amt_pat = r"[\â‚¹$â‚¬Â£]?\s*-?[\d,]+(?:\.\d{1,2})?"
    for label in labels:
        escaped = re.escape(label).replace(r"\ ", r"\s+")
        m = re.search(rf"(?im)\b{escaped}\b[^\n]{{0,30}}?({amt_pat})", text)
        if m:
            return _amount(m.group(1))
    return 0.0


def _currency(text: str) -> str:
    if "â‚¹" in text or re.search(r"\bINR\b", text, re.IGNORECASE):
        return "INR"
    if "â‚¬" in text or re.search(r"\bEUR\b", text, re.IGNORECASE):
        return "EUR"
    if "Â£" in text or re.search(r"\bGBP\b", text, re.IGNORECASE):
        return "GBP"
    return "INR"


def detect_kind(text: str, file_path: str | Path = "") -> DocumentKind:
    path_str = str(file_path).lower()
    t = text.lower()

    if re.search(r"\b(salary slip|pay statement|net pay|payslip|pay slip)\b", t):
        return "salary_slip"
    if re.search(r"\b(bank statement|account statement|opening balance|closing balance)\b", t):
        return "bank_statement"
    if re.search(r"\b(credit note|debit note|cn no|dn no)\b", t):
        return "credit_debit_note"
    if re.search(r"\b(gstr|gst return|input tax credit|itc)\b", t):
        return "gst_return"
    if re.search(r"\b(purchase order|p\.?o\.? no|delivery date|po number)\b", t):
        return "purchase_order"
    if re.search(r"\b(invoice|bill to|ship to|invoice no|invoice number)\b", t):
        return "invoice"

    if "salary_slip" in path_str or "payslip" in path_str:
        return "salary_slip"
    if "bank_statement" in path_str or "bank statement" in path_str:
        return "bank_statement"
    if "credit_debit" in path_str or "credit note" in path_str or "debit note" in path_str:
        return "credit_debit_note"
    if "gst_return" in path_str or "gstr" in path_str:
        return "gst_return"
    if "purchase_order" in path_str or "purchase order" in path_str:
        return "purchase_order"
    if "invoice" in path_str:
        return "invoice"

    return "unknown"


def _extract_salary_slip(text: str, doc: ExtractedDocument) -> None:
    doc.customer_or_employee = _find(
        r"employee\s*name\s*[:\-]?\s*(.+?)(?:\s{2,}|$)", text
    ) or _find(r"name\s*[:\-]\s*(.+?)(?:\s{2,}|\n)", text)

    doc.employee_id    = _find(r"employee\s*id\s*[:\-]?\s*([A-Z0-9\-]+)", text)
    doc.designation    = _find(r"designation\s*[:\-]?\s*(.+?)(?:\s{2,}|\n)", text)
    doc.department     = _find(r"department\s*[:\-]?\s*(.+?)(?:\s{2,}|\n)", text)
    doc.period         = _find(r"pay\s*period\s*[:\-]?\s*(.+?)(?:\s{2,}|\n)", text)
    doc.document_date  = _find(r"pay\s*date\s*[:\-]?\s*(.+?)(?:\s{2,}|\n)", text)
    doc.document_number = _find(r"slip\s*no\s*[:\-]?\s*([A-Z0-9/\-]+)", text)
    doc.bank_name      = _find(r"bank\s*[:\-]?\s*(.+?)(?:\s{2,}|\n)", text)
    doc.pan            = _find(r"pan\s*[:\-]?\s*([A-Z0-9X]+)", text)

    doc.basic_salary        = _find_amount(["basic salary", "basic"], text)
    doc.hra                 = _find_amount(["house rent allowance", "hra"], text)
    doc.conveyance          = _find_amount(["conveyance allowance", "conveyance"], text)
    doc.medical_allowance   = _find_amount(["medical allowance", "medical"], text)
    doc.special_allowance   = _find_amount(["special allowance"], text)
    doc.performance_bonus   = _find_amount(["performance bonus", "bonus"], text)
    doc.gross_amount        = _find_amount(["gross earnings", "gross salary", "gross pay", "gross"], text)
    doc.pf_employee         = _find_amount(["provident fund", "pf employee", "epf"], text)
    doc.esi                 = _find_amount(["esi contribution", "esi"], text)
    doc.tds                 = _find_amount(["income tax (tds)", "income tax", "tds"], text)
    doc.professional_tax    = _find_amount(["professional tax", "prof tax", "pt"], text)
    doc.total_deductions    = _find_amount(["total deductions", "deductions total"], text)
    doc.net_amount          = _find_amount(["net pay", "net salary", "net amount", "take home"], text)

    if doc.net_amount == 0.0 and doc.gross_amount > 0.0 and doc.total_deductions > 0.0:
        doc.net_amount = round(doc.gross_amount - doc.total_deductions, 2)
        doc.extraction_issues.append("net_pay computed from gross - deductions")


def _extract_bank_statement(text: str, doc: ExtractedDocument) -> None:
    doc.customer_or_employee = _find(r"(?:account\s*holder|name)\s*[:\-]?\s*(.+?)(?:\s{2,}|\n)", text)
    doc.account_number  = _find(r"account\s*(?:number|no\.?)\s*[:\-]?\s*([X\d\*]+)", text)
    doc.bank_name       = _find(r"(?:bank|branch)\s*[:\-]?\s*(.+?)(?:\s{2,}|\n)", text)
    doc.period          = _find(r"statement\s*period\s*[:\-]?\s*(.+?)(?:\s{2,}|\n)", text)
    doc.document_date   = _find(r"(?:generated|date)\s*[:\-]?\s*(\d{1,2}[-/]\w{2,3}[-/]\d{2,4})", text)

    doc.opening_balance = _find_amount(["opening balance", "opening bal"], text)
    doc.closing_balance = _find_amount(["closing balance", "closing bal"], text)
    doc.total_credits   = _find_amount(["total credits", "total credit"], text)
    doc.total_debits    = _find_amount(["total debits", "total debit"], text)

    doc.gross_amount = doc.total_credits
    doc.net_amount   = doc.closing_balance


def _extract_gst_return(text: str, doc: ExtractedDocument) -> None:
    doc.document_number = _find(r"(?:gstr|return|arn)\s*(?:no\.?|number)?\s*[:\-]?\s*([A-Z0-9]+)", text)
    doc.period          = _find(r"(?:tax\s*period|period)\s*[:\-]?\s*(.+?)(?:\s{2,}|\n)", text)
    doc.gstin           = _find(r"gstin\s*[:\-]?\s*([0-9A-Z]{15})", text)
    doc.vendor_or_company = _find(r"(?:legal\s*name|trade\s*name|taxpayer)\s*[:\-]?\s*(.+?)(?:\s{2,}|\n)", text)

    doc.taxable_value = _find_amount(["taxable value", "taxable turnover", "total taxable"], text)
    doc.cgst          = _find_amount(["cgst", "central gst"], text)
    doc.sgst          = _find_amount(["sgst", "state gst"], text)
    doc.igst          = _find_amount(["igst", "integrated gst"], text)
    doc.total_tax     = _find_amount(["total tax", "tax payable", "net tax"], text)
    if doc.total_tax == 0.0:
        doc.total_tax = round(doc.cgst + doc.sgst + doc.igst, 2)

    doc.gross_amount  = doc.taxable_value
    doc.tax_amount    = doc.total_tax
    doc.net_amount    = round(doc.taxable_value + doc.total_tax, 2)


def _extract_credit_debit_note(text: str, doc: ExtractedDocument) -> None:
    t = text.lower()
    doc.note_type       = "credit" if "credit note" in t else "debit" if "debit note" in t else ""
    doc.document_number = _find(r"(?:cn|dn|note)\s*(?:no\.?|number)?\s*[:\-]?\s*([A-Z0-9/\-]+)", text)
    doc.document_date   = _find(r"(?:date|note\s*date)\s*[:\-]?\s*(\d{1,2}[-/]\w+[-/]\d{2,4})", text)
    doc.original_invoice = _find(r"(?:against\s*invoice|original\s*invoice|ref\s*invoice)\s*[:\-]?\s*([A-Z0-9/\-]+)", text)
    doc.reason          = _find(r"(?:reason|narration)\s*[:\-]?\s*(.+?)(?:\n|$)", text)
    doc.vendor_or_company = _find(r"(?:vendor|seller|from|issued\s*by)\s*[:\-]?\s*(.+?)(?:\s{2,}|\n)", text)
    doc.gstin           = _find(r"gstin\s*[:\-]?\s*([0-9A-Z]{15})", text)

    doc.gross_amount  = _find_amount(["taxable amount", "subtotal", "amount before tax"], text)
    doc.tax_amount    = _find_amount(["tax", "gst", "cgst", "sgst", "igst"], text)
    doc.net_amount    = _find_amount(["total", "note value", "credit amount", "debit amount", "amount"], text)


def _extract_purchase_order(text: str, doc: ExtractedDocument) -> None:
    doc.document_number = _find(r"(?:po|purchase\s*order)\s*(?:no\.?|number)?\s*[:\-]?\s*([A-Z0-9/\-]+)", text)
    doc.document_date   = _find(r"(?:po\s*date|order\s*date|date)\s*[:\-]?\s*(\d{1,2}[-/]\w+[-/]\d{2,4})", text)
    doc.delivery_date   = _find(r"(?:delivery|required\s*by)\s*[:\-]?\s*(\d{1,2}[-/]\w+[-/]\d{2,4})", text)
    doc.payment_terms   = _find(r"payment\s*terms?\s*[:\-]?\s*(.+?)(?:\n|$)", text)
    doc.vendor_or_company = _find(r"(?:vendor|supplier|to)\s*[:\-]?\s*(.+?)(?:\s{2,}|\n)", text)
    doc.gstin           = _find(r"gstin\s*[:\-]?\s*([0-9A-Z]{15})", text)

    doc.gross_amount  = _find_amount(["subtotal", "sub total", "amount before tax"], text)
    doc.tax_amount    = _find_amount(["tax", "gst", "cgst", "sgst", "igst"], text)
    doc.net_amount    = _find_amount(["total", "grand total", "po total", "order total", "total amount"], text)

    lines = text.splitlines()
    items: list[dict] = []
    for line in lines:
        m = re.search(
            r"(?i)(?P<desc>[a-z][a-z0-9 /&().,_-]{2,}?)\s+(?P<qty>\d+(?:\.\d+)?)\s+(?P<unit>[a-z]+)?\s*(?P<price>[\d,]+(?:\.\d{1,2})?)",
            line,
        )
        if m:
            items.append({
                "description": m.group("desc").strip(),
                "quantity": float(m.group("qty")),
                "unit": (m.group("unit") or "").strip(),
                "unit_price": _amount(m.group("price")),
            })
    doc.line_items = items[:50]


def _extract_invoice(text: str, doc: ExtractedDocument) -> None:
    doc.document_number = _find(
        r"(?:invoice|bill)\s*(?:no\.?|number|#)?\s*[:\-]?\s*([A-Z0-9][A-Z0-9._/\-]{1,})", text
    )
    doc.document_date   = _find(r"(?:invoice\s*date|bill\s*date|date)\s*[:\-]?\s*(\d{1,2}[-/]\w+[-/]\d{2,4})", text)
    doc.vendor_or_company = _find(r"(?:vendor|seller|from|billed\s*by|company)\s*[:\-]?\s*(.+?)(?:\s{2,}|\n)", text)
    doc.customer_or_employee = _find(r"(?:bill\s*to|ship\s*to|customer|client)\s*[:\-]?\s*(.+?)(?:\s{2,}|\n)", text)
    doc.gstin           = _find(r"gstin\s*[:\-]?\s*([0-9A-Z]{15})", text)
    doc.pan             = _find(r"pan\s*[:\-]?\s*([A-Z]{5}[0-9]{4}[A-Z])", text)

    doc.gross_amount  = _find_amount(["subtotal", "sub total", "net amount", "amount before tax"], text)
    doc.tax_amount    = _find_amount(["total gst", "cgst", "sgst", "igst", "tax", "vat"], text)
    doc.net_amount    = _find_amount(["grand total", "total payable", "amount due", "invoice total", "total"], text)

    if doc.net_amount == 0.0 and doc.gross_amount > 0.0:
        doc.net_amount = round(doc.gross_amount + doc.tax_amount, 2)


class UniversalExtractor:

    def extract(self, text: str, file_path: str | Path = "") -> ExtractedDocument:
        cleaned = _clean(text)
        kind = detect_kind(cleaned, file_path)

        doc = ExtractedDocument(
            kind=kind,
            document_path=str(file_path),
            raw_text=cleaned,
            currency=_currency(cleaned),
        )

        if not doc.vendor_or_company:
            lines = [l.strip() for l in cleaned.splitlines() if l.strip()]
            doc.vendor_or_company = lines[0] if lines else str(Path(file_path).stem)

        dispatch = {
            "salary_slip":      _extract_salary_slip,
            "bank_statement":   _extract_bank_statement,
            "gst_return":       _extract_gst_return,
            "credit_debit_note": _extract_credit_debit_note,
            "purchase_order":   _extract_purchase_order,
            "invoice":          _extract_invoice,
        }

        handler = dispatch.get(kind, _extract_invoice)
        handler(cleaned, doc)

        return doc

    def to_invoice_fields(self, doc: ExtractedDocument) -> dict:
        return {
            "kind": doc.kind,
            "document_number": doc.document_number,
            "vendor_name": doc.vendor_or_company[:255],
            "subtotal": doc.gross_amount,
            "tax": doc.tax_amount,
            "total": doc.net_amount,
            "currency": doc.currency,
            "employee_name": doc.customer_or_employee,
            "employee_id": doc.employee_id,
            "period": doc.period,
            "net_pay": doc.net_amount,
            "gross_earnings": doc.gross_amount,
            "total_deductions": doc.total_deductions,
            "basic_salary": doc.basic_salary,
            "hra": doc.hra,
            "tds": doc.tds,
            "professional_tax": doc.professional_tax,
            "pf": doc.pf_employee,
            "opening_balance": doc.opening_balance,
            "closing_balance": doc.closing_balance,
            "total_credits": doc.total_credits,
            "total_debits": doc.total_debits,
            "cgst": doc.cgst,
            "sgst": doc.sgst,
            "igst": doc.igst,
            "taxable_value": doc.taxable_value,
            "note_type": doc.note_type,
            "original_invoice": doc.original_invoice,
            "po_number": doc.po_number,
            "delivery_date": doc.delivery_date,
            "line_items": doc.line_items,
            "gstin": doc.gstin,
            "pan": doc.pan,
            "extraction_issues": doc.extraction_issues,
        }
