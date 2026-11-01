"""Corpus inventory, grouping and explicit machine-generated review candidates."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
from pathlib import Path
import re
import sys

from core.benchmarks.contracts import Catalog, Document, Evidence, Judgment
from core.benchmarks.files import read_json, sha256_file, source_path, write_json
from core.ocr_parser import OCRParser


CATEGORIES = {"invoices", "salary_slips", "bank_statements", "gst_returns", "purchase_orders", "credit_debit_notes"}
IDENTIFIERS = {
    "invoices": r"\bInvoice\s+(?:No\.?|Number)\s*:\s*(INV-[A-Z0-9-]+)",
    "salary_slips": r"\bSlip\s+No\.?\s*:\s*(SS/[A-Z0-9/-]+)",
    "bank_statements": r"\bStatement\s+No\.?\s*:\s*(STMT-[A-Z0-9-]+)",
    "gst_returns": r"\bARN\s*:\s*([A-Z0-9]+)",
    "purchase_orders": r"\bPO\s+(?:Number|No\.?)\s*:\s*(PO-[A-Z0-9-]+)",
    "credit_debit_notes": r"\b(?:Credit|Debit)\s+Note\s+No\.?\s*:\s*([CD]N-[A-Z0-9-]+)",
}


def partition(layout):
    return "development" if layout < 6 else "regression" if layout < 8 else "holdout_candidate"


def assign_groups(documents):
    # Union entire declared layout families when any exact duplicate bridges them.
    parent = {doc.layout: doc.layout for doc in documents}

    def find(value):
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    for attribute in ("sha256", "text_sha256"):
        seen = {}
        for doc in documents:
            key = getattr(doc, attribute)
            if key is None:
                continue
            if key in seen:
                a, b = find(doc.layout), find(seen[key])
                parent[max(a, b)] = min(a, b)
            else:
                seen[key] = doc.layout
    return [doc.model_copy(update={"family": f"layout-group-{find(doc.layout)}",
                                   "partition": partition(find(doc.layout))}) for doc in documents]


def build_catalog(root: Path, progress=None) -> Catalog:
    manifest = source_path(root, "manifest.csv")
    with manifest.open(encoding="utf-8-sig", newline="") as stream:
        records = list(csv.DictReader(stream))
    parser = OCRParser(max_pdf_pages=200)
    documents = []
    for index, row in enumerate(records, 1):
        category, filename = row["doc_type"], row["filename"]
        layout = int(row["layout"])
        if category not in CATEGORIES or Path(filename).name != filename:
            raise ValueError("Unrecognized category or filename")
        relative = f"{category}/{filename}"
        if row["file"] != f"{root.name}/{relative}":
            raise ValueError("CSV path columns disagree")
        path = source_path(root, relative)
        digest = sha256_file(path)
        page_count, text_digest, error = 0, None, None
        try:
            pages = parser.parse_pdf_pages(path)
            page_count = len(pages)
            normalized = "\n".join(page.text for page in pages)
            text_digest = hashlib.sha256(normalized.encode()).hexdigest()
        except Exception as exc:
            error = type(exc).__name__
        documents.append(Document(document_id=hashlib.sha256(f"{relative}\0{digest}".encode()).hexdigest(),
            path=relative, sha256=digest, text_sha256=text_digest, category=category, layout=layout,
            family=f"layout-group-{layout}", partition=partition(layout), size_bytes=path.stat().st_size,
            pages=page_count, parse_error=error))
        if progress and index % 100 == 0:
            progress(index, len(records))
    # Unlisted files and duplicate CSV rows are errors, not silently omitted data.
    listed = {doc.path for doc in documents}
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*.pdf")}
    if listed != actual:
        raise ValueError("Source manifest does not enumerate all corpus PDFs")
    return Catalog(source_manifest_sha256=sha256_file(manifest), documents=assign_groups(documents))


def select_documents(catalog, per_category=12, seed="finsentinel-eval-v1"):
    if per_category <= 0:
        raise ValueError("Per-category sample size must be positive")
    selected = []
    for category in sorted({doc.category for doc in catalog.documents}):
        buckets = defaultdict(list)
        for doc in catalog.documents:
            if doc.category == category and doc.partition != "holdout_candidate":
                buckets[doc.layout].append(doc)
        for bucket in buckets.values():
            bucket.sort(key=lambda doc: hashlib.sha256(f"{seed}:{doc.document_id}".encode()).hexdigest())
        ordered = []
        for round_index in range(max((len(b) for b in buckets.values()), default=0)):
            ordered.extend(buckets[key][round_index] for key in sorted(buckets) if round_index < len(buckets[key]))
        if len(ordered) < per_category:
            raise ValueError(f"Insufficient non-holdout documents in {category}")
        selected.extend(ordered[:per_category])
    return selected


def make_review_queue(catalog: Catalog, root: Path, per_category=12):
    parser = OCRParser(max_pdf_pages=200)
    pending = {}
    failures = []
    selected = select_documents(catalog, per_category)
    for doc in selected:
        path = source_path(root, doc.path)
        if sha256_file(path) != doc.sha256:
            raise ValueError(f"Source hash mismatch: {doc.path}")
        try:
            pages = parser.parse_pdf_pages(path)
            matches = [(page, match) for page in pages
                       for match in re.finditer(IDENTIFIERS[doc.category], page.text, re.IGNORECASE)]
            if not matches:
                raise ValueError("Primary identifier not found")
            page, match = matches[0]
            identifier = match.group(1)
            key = (doc.category, doc.partition, identifier)
            evidence = Evidence(document_id=doc.document_id, page=page.page, start_char=match.start(1),
                                end_char=match.end(1), quote=identifier)
            pending.setdefault(key, []).append(evidence)
        except Exception as exc:
            failures.append({"document_id": doc.document_id, "reason": type(exc).__name__})
    judgments = []
    for (category, split, identifier), evidence in sorted(pending.items()):
        question = f"Find the {category.replace('_', ' ')} document identified by {identifier}."
        query_id = hashlib.sha256(f"{category}:{split}:{identifier}".encode()).hexdigest()[:20]
        judgments.append(Judgment(query_id=query_id, question=question, category=category, partition=split,
                                  intent="identifier_lookup", evidence=evidence).model_dump())
    return {"schema_version": "review-queue-v1", "catalog_manifest_sha256": catalog.source_manifest_sha256,
            "catalog_sha256": hashlib.sha256(catalog.model_dump_json().encode()).hexdigest(),
            "label_origin": "machine-generated navigation candidates; not human-reviewed ground truth",
            "selected_document_ids": [doc.document_id for doc in selected], "judgments": judgments,
            "candidate_failures": failures}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inventory = commands.add_parser("catalog")
    inventory.add_argument("--corpus", type=Path, required=True)
    inventory.add_argument("--output", type=Path, required=True)
    review = commands.add_parser("draft")
    review.add_argument("--corpus", type=Path, required=True)
    review.add_argument("--catalog", type=Path, required=True)
    review.add_argument("--per-category", type=int, default=12)
    review.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output exists; choose a new artifact path")
    if args.command == "catalog":
        result = build_catalog(args.corpus, lambda done, total: print(f"Catalogued {done}/{total}", file=sys.stderr))
        write_json(args.output, result.model_dump())
        print({"documents": len(result.documents), "partitions": dict(Counter(d.partition for d in result.documents)),
               "parse_failures": sum(d.parse_error is not None for d in result.documents)})
    else:
        result = make_review_queue(Catalog.model_validate(read_json(args.catalog)), args.corpus, args.per_category)
        write_json(args.output, result)
        print({"selected_documents": len(result["selected_document_ids"]), "draft_queries": len(result["judgments"]),
               "candidate_failures": len(result["candidate_failures"])})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
