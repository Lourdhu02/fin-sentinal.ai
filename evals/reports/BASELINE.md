# Provisional lexical baseline — 1 November 2026

This run measures identifier navigation through SQLite BM25. It does not measure
financial answer accuracy, semantic QA, generation quality or GPU performance.
All 66 query labels remain machine-generated drafts; no release gates apply.

## Corpus and working sample

| Item | Count |
|---|---:|
| PDFs inventoried and hashed | 1,000 |
| Development / regression / holdout candidates | 592 / 227 / 181 |
| PDFs with catalog parse errors | 30 |
| Non-holdout documents attempted by the benchmark | 819 |
| Successfully indexed documents / chunks | 790 / 1,766 |
| Non-holdout parse failures | 29 |
| Working sample: 12 documents in each of six categories | 72 |
| Draft queries / label-generation failures | 66 / 6 |

Sample allocation is 36 development and 36 regression documents before parsing.
The six failed candidates leave 34 development and 32 regression questions. Parse
and label-generation failures are retained in the artifacts. The report status is
`completed_with_failures` and the command exits 1 because ingestion is incomplete.

## Measured retrieval

| Slice | Queries | Document Recall@5 | MRR@5 | Evidence-span recall@5 |
|---|---:|---:|---:|---:|
| Development | 34 | 1.000 | 0.980 | 1.000 |
| Regression | 32 | 1.000 | 0.948 | 1.000 |
| Combined | 66 | 1.000 | 0.965 | 1.000 |

The combined nDCG@5 is 0.974. Salary slips are the weakest ranking slice (MRR@5
0.767), despite all labeled targets appearing within five chunks. The questions
contain exact source identifiers, making them favorable to lexical search; these
numbers must not be presented as general RAG or financial accuracy.

The lexical and authoritative vector-hit isolation canaries returned zero foreign
results. This is a narrow integration check, not a complete security assessment.

## Diagnostic observations

The existing extractor produced at least one amount observation for 295 of 819
attempted documents and detected an explicit currency for 116. These are coverage
counts, not correctness rates: observations may still contain truncated or
misinterpreted values. Independent field labels are required to score accuracy.

Rendered samples and extracted text show broken currency glyphs and totals split
across lines. Thirty catalog files raise parser errors; the first inspected error
is an unexpected end-of-file. The source files were preserved unchanged.

## Timing and resource scope

On the recorded Windows/Python 3.11 process, the complete measured parse/index/query
phase took about 40.5 seconds. Retrieval-only P50/P95 was 10.7/13.4 ms across the
66 queries. Sampled peak RSS was about 76.9 MiB. These are single-run observations
with periodic RSS sampling, not service-level targets or end-to-end chat latency.

No embedding model, reranker, generator or GPU computation ran. Environment,
dependency versions, code commit/fingerprint and configuration are recorded in
[the machine-readable report](bm25-all-nonholdout-v1.json).

## Next decisions

1. Triage the 30 malformed/parser-rejected sources, preserving original hashes;
   determine which can be recovered and which belong in an explicit failure set.
2. Independently review monetary fields, tables and semantic questions before
   changing the production extractor or measuring numerical answer quality.
3. Add payroll-specific disambiguation questions and inspect the ranking failures.
4. Compare cached embedding candidates against this same catalog and reviewed
   question set. Measure exact-search quality before benchmarking an ANN backend.
5. Acquire a separately curated, licensed blind set. The repository's public
   holdout candidates are not a substitute for that set.
