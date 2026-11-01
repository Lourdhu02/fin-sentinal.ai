from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


Partition = Literal["development", "regression", "holdout_candidate"]
Review = Literal["draft", "human_reviewed"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Document(Contract):
    document_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    text_sha256: str | None = None
    category: str
    layout: int = Field(ge=0, le=9)
    family: str
    partition: Partition
    size_bytes: int = Field(gt=0)
    pages: int = Field(ge=0)
    parse_error: str | None = None


class Catalog(Contract):
    schema_version: Literal["catalog-v1"] = "catalog-v1"
    source_manifest_sha256: str
    source_provenance: str = "repository corpus; origin and license not independently verified"
    grouping_policy: str = "declared layout ID plus exact normalized-text/binary duplicates"
    partition_policy: str = "layout 0-5 development, 6-7 regression, 8-9 holdout candidate; merged groups use lowest layout"
    documents: list[Document]

    @model_validator(mode="after")
    def unique_documents(self):
        ids = [doc.document_id for doc in self.documents]
        paths = [doc.path for doc in self.documents]
        if len(set(ids)) != len(ids) or len(set(paths)) != len(paths):
            raise ValueError("Duplicate document identity or path")
        for key in ("family", "sha256", "text_sha256"):
            partitions = {}
            for doc in self.documents:
                value = getattr(doc, key)
                if value is None:
                    continue
                partitions.setdefault(value, set()).add(doc.partition)
            if any(len(values) > 1 for values in partitions.values()):
                raise ValueError(f"Partition leakage through {key}")
        return self


class Evidence(Contract):
    document_id: str
    page: int = Field(gt=0)
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)
    quote: str = Field(min_length=1)

    @model_validator(mode="after")
    def ordered_span(self):
        if self.end_char <= self.start_char:
            raise ValueError("Evidence span is empty or reversed")
        return self


class Judgment(Contract):
    query_id: str
    question: str = Field(min_length=1, max_length=8000)
    category: str
    partition: Partition
    intent: Literal["identifier_lookup", "field_lookup"]
    review_status: Review = "draft"
    reviewer: str | None = None
    evidence: list[Evidence] = Field(min_length=1)

    @model_validator(mode="after")
    def reviewer_required(self):
        if self.review_status == "human_reviewed" and not self.reviewer:
            raise ValueError("Reviewed judgments require a reviewer")
        return self
