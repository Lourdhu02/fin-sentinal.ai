"""Build the FinSentinelAI retrieval benchmark from test-data/sugar_dataset.

Each question targets one document. The gold answer is a field value copied
from that document's own text, and the identifier in the question is checked
to occur in exactly one document of its type, so every question has one
correct source. Output is deterministic (fixed seed).

    python -m eval.build_questions            # writes eval/questions.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.ocr_parser import OCRParser  # noqa: E402

DATASET = ROOT / "test-data" / "sugar_dataset"
OUT = ROOT / "eval" / "questions.jsonl"
PER_TYPE = 10
SEED = 7


def _field(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text)
    return match.group(1).strip() if match else None


def _invoice(text: str) -> list[tuple[str, str, str]]:
    inv = _field(text, r"Invoice No:\s*(INV-\d{4}-\d{4})")
    due = _field(text, r"Due Date:\s*([A-Z][a-z]+ \d{1,2}, \d{4})")
    vendor = _field(text, r"\nFrom:\s*([^\n]+?)\s*(?:\n|$)")
    out = []
    if inv and due:
        out.append((inv, f"When is payment due for invoice {inv}?", due))
    if inv and vendor:
        out.append((inv, f"Which vendor issued invoice {inv}?", vendor))
    return out


def _bank(text: str) -> list[tuple[str, str, str]]:
    stmt = _field(text, r"Statement No:\s*(STMT-\d{6}-\d{4})")
    opening = _field(text, r"Opening Balance:\s*([\d,]+\.\d{2})")
    period = _field(text, r"Statement Period:\s*([A-Z][a-z]+ \d{2}, \d{4}) to")
    out = []
    if stmt and opening:
        out.append((stmt, f"What was the opening balance on bank statement {stmt}?", opening))
    if stmt and period:
        out.append((stmt, f"What period does bank statement {stmt} start from?", period))
    return out


def _salary(text: str) -> list[tuple[str, str, str]]:
    name = _field(text, r"Employee Name:\s*([A-Z][a-z]+ [A-Z][a-z]+)")
    period = _field(text, r"Pay Period:\s*([A-Z][a-z]+ \d{4})")
    tds = _field(text, r"Income Tax \(TDS\)\s*([\d,]+\.\d{2})")
    basic = _field(text, r"Basic Salary\s*([\d,]+\.\d{2})")
    out = []
    if name and period and tds:
        out.append((f"{name}|{period}", f"How much income tax (TDS) was deducted from {name}'s salary for {period}?", tds))
    if name and period and basic:
        out.append((f"{name}|{period}", f"What was {name}'s basic salary in {period}?", basic))
    return out


def _gst(text: str) -> list[tuple[str, str, str]]:
    arn = _field(text, r"ARN:\s*([A-Z0-9]{10,})")
    form = _field(text, r"Form Type:\s*(GSTR-[0-9A-Z]+)")
    period = _field(text, r"Tax Period:\s*([A-Z][a-z]+ \d{4})")
    filed = _field(text, r"Filing Date:\s*([A-Z][a-z]+ \d{2}, \d{4})")
    out = []
    if arn and filed:
        out.append((arn, f"On what date was the GST return with ARN {arn} filed?", filed))
    if arn and form and period:
        out.append((arn, f"Which tax period does GST return {arn} cover?", period))
    return out


def _po(text: str) -> list[tuple[str, str, str]]:
    po = _field(text, r"PO Number:\s*(PO-\d{4}-\d{4})")
    vendor = _field(text, r"\nVendor:\s*(.+?)\s+Delivery By:")
    terms = _field(text, r"Payment Terms:\s*(Net \d+|[A-Za-z ]+?)\s*(?:\n|$)")
    out = []
    if po and vendor:
        out.append((po, f"Which vendor is purchase order {po} placed with?", vendor))
    if po and terms:
        out.append((po, f"What are the payment terms on purchase order {po}?", terms))
    return out


def _note(text: str) -> list[tuple[str, str, str]]:
    note = _field(text, r"(?:Credit|Debit) Note No:\s*([CD]N-\d{4}-\d{4})")
    reason = _field(text, r"Reason:\s*(.+?)\s+Place of Supply")
    party = _field(text, r"Party Name:\s*(.+?)\s+GSTIN:")
    out = []
    if note and reason:
        out.append((note, f"Why was note {note} issued?", reason))
    if note and party:
        out.append((note, f"Which party is note {note} issued to?", party))
    return out


EXTRACTORS = {
    "invoices": _invoice,
    "bank_statements": _bank,
    "salary_slips": _salary,
    "gst_returns": _gst,
    "purchase_orders": _po,
    "credit_debit_notes": _note,
}


def build(per_type: int = PER_TYPE, seed: int = SEED) -> list[dict]:
    parser = OCRParser()
    rng = random.Random(seed)
    questions: list[dict] = []
    for doc_type, extract in EXTRACTORS.items():
        files = sorted((DATASET / doc_type).glob("*.pdf"))
        texts = {f: parser.parse_path(f) for f in files}
        candidates = {f: extract(t) for f, t in texts.items()}
        key_counts = Counter(key for cands in candidates.values() for key in {c[0] for c in cands})
        pool = [
            (f, q, a)
            for f, cands in candidates.items()
            for key, q, a in cands
            if key_counts[key] == 1 and a in texts[f]
        ]
        by_file: dict[Path, list[tuple[str, str]]] = {}
        for f, q, a in pool:
            by_file.setdefault(f, []).append((q, a))
        chosen = rng.sample(sorted(by_file), min(per_type, len(by_file)))
        for f in chosen:
            q, a = rng.choice(by_file[f])
            questions.append({
                "id": f"{doc_type}-{len(questions):03d}",
                "doc_type": doc_type,
                "question": q,
                "answer": a,
                "gold_file": f.name,
            })
    return questions


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--per-type", type=int, default=PER_TYPE)
    ap.add_argument("--output", type=Path, default=OUT)
    args = ap.parse_args(argv)
    questions = build(args.per_type)
    args.output.write_text("".join(json.dumps(q) + "\n" for q in questions), encoding="utf-8")
    print(f"{len(questions)} questions -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
