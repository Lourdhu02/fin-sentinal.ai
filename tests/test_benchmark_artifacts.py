from collections import Counter
import csv
from pathlib import Path

from core.benchmarks.contracts import Catalog
from core.benchmarks.files import read_json, sha256_file, source_path
from core.benchmarks.runner import validate_queue


ROOT = Path(__file__).resolve().parents[1]


def test_catalog_matches_source_manifest_and_every_source_hash():
    corpus = ROOT / "test-data/sugar_dataset"
    catalog = Catalog.model_validate(read_json(ROOT / "evals/datasets/catalog-v1.json"))
    manifest = corpus / "manifest.csv"
    assert catalog.source_manifest_sha256 == sha256_file(manifest)
    with manifest.open(encoding="utf-8-sig", newline="") as stream:
        assert len(catalog.documents) == len(list(csv.DictReader(stream)))
    for doc in catalog.documents:
        assert sha256_file(source_path(corpus, doc.path)) == doc.sha256


def test_review_sample_balances_partitions_and_accounts_for_candidates():
    corpus = ROOT / "test-data/sugar_dataset"
    catalog = Catalog.model_validate(read_json(ROOT / "evals/datasets/catalog-v1.json"))
    queue = read_json(ROOT / "evals/datasets/review-queue-v2.json")
    judgments, docs = validate_queue(catalog, queue, corpus, "all_nonholdout", allow_draft=True)
    selected = queue["selected_document_ids"]
    assert len(selected) == len(set(selected)) == 72
    assert all(count == 12 for count in Counter(docs[key].category for key in selected).values())
    assert Counter(docs[key].partition for key in selected) == {"development": 36, "regression": 36}
    labeled = {e.document_id for judgment in judgments for e in judgment.evidence}
    failed = {row["document_id"] for row in queue["candidate_failures"]}
    assert labeled.isdisjoint(failed)
    assert labeled | failed == set(selected)
    assert all(judgment.review_status == "draft" for judgment in judgments)
