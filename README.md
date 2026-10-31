# FinSentinelAI

Local financial-document search with FastAPI, React, SQLite, Chroma and a local
Ollama or llama.cpp server. This implementation adds isolation, recoverable
ingestion, page provenance, hybrid retrieval and reference validation.

## Install

Requires Python 3.11+, uv, Node 22+, and a separately installed local inference
runtime. Tesseract is required for scanned PDFs and images. Native-text PDFs do
not require Tesseract.

```powershell
uv sync --locked --extra local --extra test
Copy-Item .env.example .env
```

Before offline use, provision the configured SentenceTransformers embedding and
reranker models once, or configure local model directories. Provision the Ollama
model separately. Model weights are not included in this repository or lockfile.
The default embedding is `all-MiniLM-L6-v2`; the optional reranker is
`cross-encoder/ms-marco-MiniLM-L-6-v2`.

```powershell
uv run --no-sync python -m cli.bootstrap
uv run --no-sync uvicorn api.main:app --host 127.0.0.1 --port 8000 --env-file .env
```

Bootstrap prompts for an admin password and never overwrites an existing account.
It is optional when development registration is enabled. Passwords for new
accounts require 12 characters and must fit bcrypt's 72-byte limit.

```powershell
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173. `VITE_API_URL` overrides the backend base URL.

## Runtime behavior

- One API application; `api.app` is a compatibility import of `api.main`.
- Expensive models load lazily, once per process. Run one API worker on a laptop.
- CPU embeddings and reranking; generation placement is controlled by Ollama or
  llama.cpp. GPU visibility is reported, not an automatic offload guarantee.
- Uploads are streamed into staging, size-limited, signature-checked and published
  exclusively. Same-name uploads require explicit deletion before replacement.
- PDFs preserve page numbers and parser identity. Empty pages use bounded OCR;
  unreadable documents are marked failed rather than indexed as empty text.
- SQLite stores document state, exact source observations, chunks and BM25 text.
  Chroma is a rebuildable dense index. Queries fuse lexical and dense rankings.
- SQL ownership checks reauthorize vector hits. Failed/deleting records cannot
  contribute evidence. Conversation history is bounded and user-scoped.
- Answers require valid `[source:chunk-id]` references. This checks reference
  validity, **not semantic entailment or numeric claim correctness**.

Source observations preserve decimal strings and offsets. `core.finance` provides
exact money arithmetic. Legacy invoice `REAL` fields remain compatibility data;
they are not an authoritative ledger. Verified aggregation and reconciliation
query tools are not yet exposed by the chat API.

## Local inference

Set `FINSENTINEL_INFERENCE=ollama` (default), or `llamacpp` with a running
OpenAI-compatible llama-server. Only numeric loopback HTTP endpoints are accepted;
proxies and redirects are disabled. Provision and select the server's model
explicitly. No models are downloaded automatically by the application in its
default offline model-loading mode.

For Ollama, set `OLLAMA_NO_CLOUD=1` in the environment of the **Ollama process**.
Set `HF_HUB_OFFLINE=1` and `HF_HUB_DISABLE_TELEMETRY=1` for offline model loading.
An outbound-denied end-to-end acceptance run is still required before claiming
complete offline operation. See [operations](docs/OPERATIONS.md).

## Verification

```powershell
uv sync --locked --extra test --extra storage
uv run --no-sync pytest -q
uv run --no-sync ruff check .
uv build
```

The storage extra enables real Chroma and six-category PDF smoke tests without
installing generation weights. This verification sync does not install ML
generation dependencies; repeat the local sync before running the full app.

Frontend: `npm run lint`, `npm run build`, and `npm audit --omit=dev`.
CI defines Windows/Linux and Python 3.11/3.12 jobs; only the local Windows checks
have been run during implementation.

See [implementation status](docs/IMPLEMENTATION.md), [evaluation](evals/README.md),
[API](api.md), and [model experiments](model.md).
