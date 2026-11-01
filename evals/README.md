# Evaluation workspace

The evaluation runner executes real retrieval in isolated temporary SQLite
storage. It never indexes into the application's runtime database. Every run
checks source hashes and evidence spans and records its code/configuration,
dependencies, failures, timing and sampled memory.

## Current artifacts

| Artifact | Purpose |
|---|---|
| [catalog-v1.json](datasets/catalog-v1.json) | Inventory and byte/text hashes for all 1,000 corpus PDFs |
| [review-queue-v2.json](datasets/review-queue-v2.json) | Current 72-document working sample; 66 draft navigation questions and six explicit candidate failures |
| [bm25-all-nonholdout-v1.json](reports/bm25-all-nonholdout-v1.json) | Provisional BM25 baseline over all 819 non-holdout documents |
| [Baseline interpretation](reports/BASELINE.md) | Results, scope, failures and next decisions |

`review-queue-v1.json` and `bm25-regression-v1.json` retain the initial pilot for
traceability. The v2 sample allocates six development and six regression documents
per category, with round-robin coverage of their declared layouts. The sample
contains 12 documents per category regardless of whether parsing succeeds.

These are machine-generated **draft identifier-navigation labels**. They are not
human-reviewed ground truth, a semantic QA benchmark, financial-field labels, or
a release-quality certification. Draft runs require explicit opt-in.

## Reproduce the baseline

From the repository root:

```powershell
uv sync --locked --extra test --extra storage --extra eval
uv run --no-sync python -m core.benchmarks.runner --corpus test-data/sugar_dataset --catalog evals/datasets/catalog-v1.json --judgments evals/datasets/review-queue-v2.json --partition all_nonholdout --mode bm25 --k 5 --allow-draft --output runtime/evaluation/bm25-rerun.json
```

Outputs are published exclusively: an existing file is never overwritten. Choose
a new output name for each run. The current corpus has parsing failures, so the
runner writes a `completed_with_failures` report and returns **exit code 1**. That
is an explicit incomplete-ingestion result, not a successful release gate.

Use `--partition development` or `--partition regression` for separate runs.
The combined profile also reports each partition and category separately. Failed
queries remain in metric denominators. Documents that cannot produce labels are
recorded separately; they never become fabricated retrieval questions.

## Build a new catalog and review queue

```powershell
uv run --no-sync python -m core.benchmarks.dataset catalog --corpus test-data/sugar_dataset --output runtime/evaluation/catalog-rerun.json
uv run --no-sync python -m core.benchmarks.dataset draft --corpus test-data/sugar_dataset --catalog runtime/evaluation/catalog-rerun.json --per-category 12 --output runtime/evaluation/review-rerun.json
```

Grouping occurs **before** partition assignment. The catalog keeps every declared
layout ID in one partition, merging entire groups when exact binary or normalized
text duplicates cross layouts. Layouts 0–5 map to development, 6–7 to regression,
and 8–9 to holdout candidates unless duplicate grouping merges them.

This prevents known group/exact-duplicate leakage. It does not prove there are no
near-duplicate templates. The public corpus is not a blind set. Holdout-candidate
questions require `--allow-holdout`; accessing them for tuning consumes that
holdout. Source/license provenance remains unverified until independently checked.

## Review the labels

Each judgment records a question, category, partition, source document ID, page,
exact quote, and start/end character offsets in the normalized page text. Link
the document ID to its path in the catalog and inspect the original page.

1. Confirm the identifier describes the requested document, not a reference to a
   different invoice, order or employee record.
2. Check the quoted span and page against the PDF, including ambiguous characters.
3. Resolve duplicate identifiers by including all relevant evidence or clarifying
   the question.
4. Add independently written semantic and financial questions with reviewed
   source values. Never generate expected amounts with the extractor being graded.
5. Set `review_status` to `human_reviewed` and record a reviewer only after that
   review occurs. Preserve previous artifacts and publish a new version.

Generate a first-page overview of one source per category:

```powershell
uv run --no-sync python -m core.benchmarks.preview --corpus test-data/sugar_dataset --output runtime/evaluation/source-preview.png
```

This overview supports initial inspection; it is not a substitute for reviewing
all selected documents at readable resolution.

## Optional dense and hybrid profiles

Use `--mode dense` or `--mode hybrid` with `--embedding-directory` pointing to a
provisioned local SentenceTransformers directory. Install the application `local`
extra together with `test`, `storage`, and `eval` first. No model downloads or
random embeddings are permitted by the runner.

The runner hashes the model directory and uses CPU embeddings with an exact NumPy
dot-product index. This isolates embedding/retrieval quality from approximate-index
behavior. It is **not a Chroma ANN performance benchmark**. BM25 uses the same
SQLite repository search as the application. The hybrid profile uses the shared
reciprocal-rank-fusion implementation. No reranker or generator runs in this phase.

Reports separate corpus ingestion, SQLite indexing, embedding initialization/index
time and query latency. RSS is sampled for the benchmark process every 50 ms;
subprocess memory and GPU peak memory are not measured. `--trace-python-heap` adds
optional Python allocation tracing and its overhead. Hardware visibility does not
establish GPU offload.

## Existing judgment scorer

`python -m core.evaluation judgments.jsonl --k 5` still scores externally supplied
rankings in the simple JSONL format:

```json
{"expected":["relevant-id"],"retrieved":["first-result-id","relevant-id"]}
```

Duplicates consume rank positions without earning extra credit. The executable
benchmark additionally reports document ranking and complete evidence-span recall.

See [the implementation plan](../docs/EVALUATION_PLAN.md) for acceptance boundaries.
