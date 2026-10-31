# Evaluation contract

Keep three template-separated partitions: development, regression, blind holdout.
Deduplicate documents and near-duplicate templates before splitting. Never tune
on the blind partition. Production customer documents require explicit curation.

Each manifest record contains document SHA-256, source/license, template family,
language, scan quality, tenant, expected fields and reviewed evidence IDs.

Export retrieval judgments as JSONL:

```json
{"expected":["relevant-chunk-id"],"retrieved":["first-result-id","relevant-chunk-id"]}
```

Run `python -m core.evaluation judgments.jsonl --k 5`. This computes metrics from
provided predictions; it does not execute retrieval or establish answer quality.
Store model revision, artifact hash, runtime version, parser/chunker version,
hardware and context size beside each report. Include failed queries.

Quality gates: zero isolation failures; exact deterministic money fixtures;
separate field, retrieval, citation and abstention metrics. Choose latency and
memory budgets from the target hardware baseline. No golden labels have been
invented for the existing synthetic corpus.
