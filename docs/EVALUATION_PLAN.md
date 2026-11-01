# Evaluation implementation plan

## Objective

Produce an auditable baseline before changing models or extraction rules. A run
must identify its source documents, code, configuration, judgments, execution
mode and failures. Performance measurements describe the measured process only.

## Deliverables and acceptance

1. **Corpus catalog:** verify the existing CSV against source PDFs, hash bytes and
   extracted text, record parse failures, and group declared layouts and exact
   normalized-text duplicates before assigning partitions. Unknown source license
   and label provenance stay unknown.
2. **Representative working set:** deterministically select 12 documents per
   category from development/regression groups. Reserve holdout-candidate groups;
   the public repository corpus is never called a blind test set.
3. **Review queue:** generate identifier lookup questions with exact page/text
   spans. Mark these draft machine labels. A human reviewer must verify evidence,
   broaden question types, and approve labels before release gates apply.
4. **Runner:** execute actual SQLite BM25 retrieval in temporary storage. Optional
   dense/hybrid profiles use cached real embeddings and Chroma, never random
   vectors. Score evidence-span hits, rank metrics, failure rates and isolation
   canaries. Keep failed questions in denominators and report slices by category.
5. **Measurements:** separate parse, index, retrieval and model initialization
   timing; sample process RSS and Python heap separately. Record hardware and
   dependency versions. No generation, numeric correctness or GPU-throughput
   scores without the relevant model/labels.
6. **Verification:** test split leakage, source tampering, invalid evidence spans,
   duplicate predictions, failed-query denominators, denied cross-user retrieval,
   and the executable CLI. Run and publish a provisional lexical baseline.

## Boundaries

Do not modify application extraction behavior to improve this first baseline.
Do not infer labels from `extract_facts` and then grade that function against its
own output. Extraction coverage is diagnostic until independent field labels
exist. Draft identifier queries measure navigation, not semantic QA.

Grouping by the supplied layout ID and exact normalized text reduces known
leakage; it does not prove the absence of near-duplicate templates. A holdout
becomes development data once inspected for tuning. A true blind set must be
curated separately, with its license and review history recorded.

## Next decision

Use the measured error slices to choose between extraction/layout improvements,
retrieval tuning and model experiments. Approve numeric and semantic answer
tests before promoting a new generator or publishing financial-accuracy claims.
