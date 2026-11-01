import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.benchmarks.contracts import Catalog, Document, Evidence, Judgment
from core.benchmarks.dataset import assign_groups, select_documents
from core.benchmarks.files import source_path, write_json


def document(name="a.pdf", layout=0, digest=None, category="invoices"):
    digest = digest or hashlib.sha256(name.encode()).hexdigest()
    return Document(document_id=hashlib.sha256((name + digest).encode()).hexdigest(), path=name,
                    sha256=digest, text_sha256=digest, category=category, layout=layout,
                    family=f"layout-{layout}", partition="development" if layout < 6 else "regression",
                    size_bytes=1, pages=1)


def test_exact_duplicates_merge_layout_families_before_split():
    a, b, c = document("a.pdf", 0), document("b.pdf", 7), document("c.pdf", 7)
    b = b.model_copy(update={"text_sha256": a.text_sha256})
    grouped = assign_groups([a, b, c])
    assert {d.partition for d in grouped} == {"development"}
    assert len({d.family for d in grouped}) == 1


def test_catalog_rejects_duplicate_leakage():
    a = document()
    b = document("b.pdf", 7, digest=a.sha256)
    with pytest.raises(ValidationError, match="leakage"):
        Catalog(source_manifest_sha256="abc", documents=[a, b])


def test_sample_is_deterministic_and_excludes_holdout():
    docs = [document(f"{i}.pdf", i % 10) for i in range(30)]
    catalog = Catalog(source_manifest_sha256="abc", documents=assign_groups(docs))
    selected = select_documents(catalog, per_category=12)
    assert selected == select_documents(catalog, per_category=12)
    assert len(selected) == 12
    assert all(d.partition != "holdout_candidate" for d in selected)
    assert {d.layout for d in selected} == set(range(8))
    assert sum(d.partition == "development" for d in selected) == 6
    assert sum(d.partition == "regression" for d in selected) == 6


@pytest.mark.parametrize("path", ["../secret", "/absolute", "..\\secret", "C:secret"])
def test_source_path_containment(path, tmp_path):
    with pytest.raises(ValueError):
        source_path(tmp_path, path)


def test_artifacts_never_overwrite_previous_reports(tmp_path):
    path = tmp_path / "report.json"
    write_json(path, {"value": 1})
    with pytest.raises(FileExistsError):
        write_json(path, {"value": 2})
    assert '"value": 1' in path.read_text()
    assert len(list(tmp_path.iterdir())) == 1


def test_review_requires_reviewer_and_ordered_evidence():
    with pytest.raises(ValidationError):
        Evidence(document_id="a", page=1, start_char=4, end_char=2, quote="x")
    with pytest.raises(ValidationError, match="reviewer"):
        Judgment(query_id="q", question="Find invoice", category="invoices", partition="regression",
                 intent="identifier_lookup", review_status="human_reviewed", evidence=[
                     Evidence(document_id="a", page=1, start_char=0, end_char=1, quote="x")])
