import re


def verify_citations(response: str, evidence: list[dict]) -> bool:
    """Validate references, not semantic entailment; that needs separate evaluation."""
    cited = re.findall(r"\[source:([a-f0-9]{64})\]", response)
    allowed = {item["chunk_id"] for item in evidence}
    return bool(cited) and all(key in allowed for key in cited)
