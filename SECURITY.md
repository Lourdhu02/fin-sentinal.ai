# Security boundaries and current limitations

Authentication uses bcrypt and expiring JWTs. Production requires explicit
non-default signing/encryption secrets and disables public registration unless
explicitly configured. Disabled accounts cannot authenticate or reuse tokens.

Document metadata, lexical queries, vector hits and conversation histories are
scoped to authenticated users. Model prompts do not decide access permissions.
Uploaded names reject Windows and POSIX path components, device names and alternate
data-stream syntax. Resolved targets must remain inside the user's directory.

Audit query/response content is encrypted with AES-GCM. Original uploads, SQLite
document/chunk text, and Chroma data are **not encrypted by the application**.
Protect the runtime directory and backups with OS access controls and disk
encryption. Preserve `.jwt_secret` and `.encryption_key` with backups; losing the
latter makes old encrypted audit records unreadable. Windows chmod does not
replace an explicit directory ACL policy.

The application restricts inference HTTP traffic to numeric loopback addresses
and disables proxy/redirect handling. Separate inference services and model
libraries require their own offline settings and egress verification.

Citation validation proves reference existence and tenant ownership, not claim
truth. Prompt injection resistance is partial. Treat generated financial answers
as source-assisted explanations pending deterministic claim verification.

Current deployment scope is a trusted local machine with one API worker. Public
network deployment still requires request-body limits before multipart parsing,
rate limiting, hardened sessions, dependency review and additional threat testing.
Per-file limits apply after the framework has parsed multipart data. OCR has a
subprocess timeout but PDF parsing is not sandboxed. High-risk files need isolation.

Report vulnerabilities privately to the repository maintainers. Do not attach
real financial documents, keys, tokens or decrypted audit logs to public issues.
