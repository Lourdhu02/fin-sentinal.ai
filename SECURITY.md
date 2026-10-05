# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.0.x   | Yes       |

## Reporting a Vulnerability

If you discover a security vulnerability in FinSentinelAI, please report it responsibly:

1. **Do not** open a public GitHub issue for security vulnerabilities.
2. Email the maintainers with a detailed description of the vulnerability.
3. Include steps to reproduce the issue if possible.
4. Allow reasonable time for a fix before public disclosure.

## Security Architecture

- All data processing runs 100% locally (no external API calls).
- Passwords are hashed with bcrypt via passlib.
- Sessions use stateless JWT tokens with configurable expiry.
- Isolation is enforced per layer:
  - **Identity:** every request is authenticated via JWT; `session_id` is derived server-side from the verified token, never from client input.
  - **Retrieval:** ChromaDB queries are always issued with a `session_id` metadata filter; the low-level `Retriever.retrieve()` requires an explicit filter argument so unfiltered search cannot be wired in silently.
  - **Conversational state:** chat history is keyed per session inside the pipeline; prompts sent to the LLM contain only the calling session's turns, and `/chat/reset` clears only the calling session.
  - **Audit trail:** stored chunks carry both `session_id` and `user_id` metadata so ownership is independently verifiable.
- File uploads are sanitized to prevent path traversal attacks.
- CORS origins are configurable via environment variables.

### Known scope limitations

- Guarantees above apply to single-process deployments. Running multiple workers/processes against a shared vector store without per-worker review is out of scope of the current verification.
- Audit logs store encrypted query/response text but are not currently scoped or access-controlled per user at the API layer.
- These properties are enforced by code and verified by the multi-user test harness (`tests/test_isolation.py`); they are not formal proofs.
