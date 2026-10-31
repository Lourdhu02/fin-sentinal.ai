# Local intelligence implementation

This series strengthens the existing modular application before introducing new
model stacks. Each milestone is independently committed and verified.

1. Package metadata and isolated test tooling.
2. Validated runtime settings and offline model loading.
3. One API composition root, tenant and conversation boundaries.
4. Safe bounded uploads, recoverable ingestion, deterministic identifiers.
5. Exact financial primitives and persisted document provenance.
6. Lexical/dense retrieval, stable citations and evaluation tooling.
7. Hardware diagnostics, CI and operational documentation.

Model downloads, runtime changes and GPU performance claims require separate
hardware experiments. The default generator remains compatible with Ollama.
Financial facts remain source observations until validated; calculations use
Decimal. Legacy invoice storage is retained for compatibility and must not be
used as an authoritative ledger.

Verification uses isolated temporary storage and injected model doubles. Actual
offline and GPU acceptance require pre-provisioned artifacts and blocked egress
on the target host; unit tests do not establish those properties.

## Completed foundation

Package/lock/CI, secure local secrets, one lazy API composition root, active-account
checks, bounded per-user conversations, safe uploads/deletion, PDF OCR fallback,
page/offset provenance, Decimal money primitives, exact source observations,
tenant document registry, idempotent ingestion, authoritative evidence checks,
BM25+dense fusion, reference validation, local inference adapters, capability
diagnostics, evaluation scoring and client error handling are implemented.

See OPERATIONS.md for verification and migration limits. The next development
slice is a reviewed evaluation corpus followed by parser/model experiments and
verified structured calculations. Hardware-aware model selection remains a plan.
