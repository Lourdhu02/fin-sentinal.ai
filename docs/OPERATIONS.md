# Operating and migrating local storage

## Existing installations

Back up the entire runtime directory with the app stopped. This release adds
`documents_v1`, `chunks_v1` and an FTS5 index without rewriting legacy invoices.
Legacy Chroma chunks have no authoritative registry records and are deliberately
excluded from retrieval. They are not silently deleted or assigned ownership.

Reingest original source documents under the intended authenticated account.
If the physical upload filename already exists, use the document DELETE endpoint
first or ingest the backed-up source through the CLI. Do not delete originals
until the new registry reports indexed and retrieval is verified.

Old JWTs signed with the former deterministic default stop working. Existing
audit records encrypted using a former key require that original key; this series
does not attempt automatic key recovery or re-encryption.

## Recovery and consistency

Ingestion states are processing, indexed, failed and deleting. Vector writes and
SQLite commits cannot share one transaction. Queries authorize vector IDs against
SQLite and ignore non-indexed records. Retry ingestion with unchanged content to
recover an interrupted write; indexed documents are idempotent. Changed content
under the same name requires explicit deletion. Source versions use content hashes;
multiple historical versions under one name are not retained automatically.

Delete removes vectors and registry state before removing an uploaded file.
If filesystem deletion fails, the file remains but is no longer queryable. Retry
DELETE after resolving the filesystem error. The CLI never deletes its source.
Deletion resets the user's conversation; histories are process-local and vanish
on restart. Run one API worker so these locks and histories have consistent scope.

Back up SQLite, uploads, Chroma and key files together while stopped. Restore to
a separate directory, set runtime/database paths, and test login, known-evidence
retrieval, per-user isolation and audit decryption before replacing active data.

## Offline acceptance

Provision model files online first; record paths, revisions, hashes and licenses.
Disable Ollama cloud in the Ollama service environment. Enable Hugging Face offline
and no-telemetry flags in the application environment. Restart with outbound
networking denied. Exercise login, upload, scanned OCR, retrieval, generation,
reset and deletion; monitor DNS/outbound attempts. Missing artifacts must produce
explicit failure. This acceptance procedure has not yet been run on GPU models.

## Verification recorded during implementation

Windows / Python 3.11: 70 tests passed, including real Chroma CRUD/filtering, sample
PDF parsing in six document categories, and API end-to-end tests with injected
models. Ruff, frontend ESLint, frontend production build and Python wheel/sdist
build passed. Production npm audit: zero findings after compatible updates.
Six moderate findings remain in development ESLint/minimatch dependencies; npm
reported no compatible automatic fix. Linux/matrix checks await CI execution.

Tests do not establish financial answer accuracy, real-model latency, GPU fitting,
whole-corpus parsing quality or offline egress guarantees. See the evaluation
contract before publishing any such metrics.
