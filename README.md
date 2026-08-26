# FinSentinelAI

<div align="center">
  <img src="https://img.shields.io/badge/Status-v1.0.0-success.svg" alt="Version 1.0.0">
  <img src="https://img.shields.io/badge/Architecture-React%20%2B%20FastAPI%20%2B%20ChromaDB-blue" alt="Architecture">
  <img src="https://img.shields.io/badge/Security-JWT%20Isolated-blueviolet" alt="Security">
</div>

<br>

**FinSentinelAI** is an enterprise-grade, privacy-first AI financial document intelligence platform. It runs 100% locally to process, index, and query highly sensitive financial documents (invoices, receipts, bank statements) using advanced RAG (Retrieval-Augmented Generation) and local LLMs.

---

## Features (v1.0.0)

* **Top 1% Minimalist UI:** Ultra-premium, Apple-inspired React Single Page Application built with Vite and TailwindCSS v3.
* **100% Local & Private:** No API calls to OpenAI or Anthropic. All documents, embeddings, and chat interactions stay completely on your machine.
* **Decoupled Architecture:** High-performance asynchronous FastAPI backend communicating seamlessly with a React frontend via REST APIs.
* **User Isolation:** Secure JWT-based authentication. Every user gets a private workspace.
* **ChromaDB Vector Store:** Blazing fast vector retrieval with native database-level metadata filtering (every query is filtered server-side by the authenticated user's session).
* **Multi-Modal Support:** Automatically extracts text from PDFs, CSVs, JSONs, and images (using local Vision-Language Models).

---

## Architecture Flow

Below is the high-level system architecture of FinSentinelAI:

```mermaid
graph TD
    subgraph Frontend ["Frontend (React + TailwindCSS)"]
        UI[User Interface]
        AuthUI[Auth & Session]
    end
    
    subgraph Backend ["Backend (FastAPI)"]
        API[REST API Router]
        Auth[JWT Authentication]
        Pipeline[RAG Pipeline Core]
        Ingestion[Universal Extractor]
    end
    
    subgraph Storage ["Data Layer"]
        SQL[(SQLite User/Meta DB)]
        VDB[(ChromaDB Vector Store)]
    end
    
    subgraph AI ["Local AI Engine"]
        Emb[SentenceTransformers]
        LLM[Ollama Local LLM]
    end

    UI <-->|HTTP/JSON| API
    AuthUI --> Auth
    API --> Auth
    API --> Pipeline
    Pipeline --> Ingestion
    Pipeline <--> SQL
    Pipeline <--> VDB
    Pipeline <--> Emb
    Pipeline <--> LLM
```

---

## Getting Started

### Prerequisites
* Python 3.10+
* Node.js v18+ & npm
* [Ollama](https://ollama.ai/) installed and running locally with your model of choice.

### 1. Backend Setup

```powershell
# Clone the repository
git clone https://github.com/Lourdhu02/FinSentinal.AI.git
cd FinSentinal.AI

# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\activate

# Install requirements
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env and set FINSENTINEL_JWT_SECRET to a random secret

# Initialize database and admin user
python setup.py

# Start the FastAPI Server (runs on http://localhost:8000)
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

### 2. Frontend Setup

Open a new terminal window:

```powershell
# Navigate to the frontend directory
cd frontend

# Install Node dependencies
npm install

# Start the React Dev Server (runs on http://localhost:5173)
npm run dev
```

### 3. Usage

1. Open your browser to `http://localhost:5173`.
2. Click **Create an account** on the login screen.
3. Access your private **Document Dashboard**.
4. Upload financial documents.
5. Navigate to the **Assistant Chat** to securely query your data using local AI.

---

## Security & Privacy
FinSentinelAI enforces security boundaries in layers:
* Passwords are irreversibly hashed using `bcrypt`.
* Sessions are stateless and validated via JWT access tokens.
* **Retrieval isolation:** `session_id` is always derived server-side from the JWT-authenticated user (never from client input), and every vector search is filtered by it, so one user's documents are not retrievable by another user.
* **Conversation isolation:** chat history is stored per-session and only the calling session's turns are included in an LLM prompt; `/chat/reset` clears exactly one session.

Scope note: these guarantees are enforced at the retrieval and application-state layers of a single-process deployment. They are property-based design guarantees, not formal proofs — see `tests/test_isolation.py` for the multi-user harness that verifies them empirically.

---

## License
MIT License. See `LICENSE` for more information.

## Fin Sentinel AI
Financial AI monitoring and analysis
