# API

Interactive schema: `GET /docs`; machine-readable schema: `GET /openapi.json`.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/register` | Register if enabled; JSON username/password |
| POST | `/api/auth/login` | OAuth2 form username/password; returns JWT |
| GET | `/api/auth/me` | Current active account |
| POST | `/api/documents/upload` | Multipart `files`; inspect each result status |
| GET | `/api/documents/list` | Filenames and processing status |
| DELETE | `/api/documents/{filename}` | Delete own metadata, vectors and uploaded file |
| POST | `/api/chat/` | JSON `query`; response and source IDs/pages |
| POST | `/api/chat/reset` | Reset only the current user's history |
| GET | `/api/health` | Liveness; does not load models |
| GET | `/api/health/ready` | Authenticated initialization status; no generator probe |
| GET | `/api/system/capabilities` | Authenticated CPU/GPU visibility and configuration |

Except login, registration, liveness and API schema routes, endpoints require
`Authorization: Bearer <token>`. Model resources load on document/chat requests.
Initialization/generation unavailability returns 503. Upload processing failures
can appear in a 200 response as per-file `status: error`; clients must inspect it.
All responses include a server-generated `X-Request-ID` for local diagnostics.
