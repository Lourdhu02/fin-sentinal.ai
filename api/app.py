from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from core.pipeline import FinSentinelPipeline
from database.db_manager import DatabaseManager
from security.auth import AuthManager
from security.rbac import RBACManager

app = FastAPI(title="FinSentinelAI", version="2.0.0")
bearer = HTTPBearer()

_pipeline: FinSentinelPipeline | None = None


def get_pipeline() -> FinSentinelPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = FinSentinelPipeline()
    return _pipeline


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    auth = AuthManager()
    try:
        payload = auth.decode_token(credentials.credentials)
        return payload
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


class LoginRequest(BaseModel):
    username: str
    password: str


class QueryRequest(BaseModel):
    question: str
    top_k: int = 20


@app.post("/auth/login")
def login(req: LoginRequest):
    db = DatabaseManager()
    auth = AuthManager()
    user = auth.authenticate_user(db, req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = auth.create_access_token(user)
    return {"access_token": token, "token_type": "bearer", "role": user.role}


def _session_for(current_user: dict) -> str:
    """Derive the per-user session id server-side from verified JWT claims."""
    return f"user_{current_user.get('user_id')}_default"


@app.post("/query")
def query(req: QueryRequest, current_user=Depends(get_current_user), pipeline=Depends(get_pipeline)):
    RBACManager().require_permission(current_user, "chat")
    result = pipeline.query(
        req.question,
        session_id=_session_for(current_user),
        user_id=current_user.get("user_id"),
        top_k=req.top_k,
    )
    return result


@app.post("/conversation/reset")
def reset_conversation(current_user=Depends(get_current_user), pipeline=Depends(get_pipeline)):
    cleared = pipeline.reset_conversation(_session_for(current_user))
    return {"status": "conversation reset", "cleared_turns": cleared}


@app.get("/invoices")
def list_invoices(current_user=Depends(get_current_user)):
    db = DatabaseManager()
    invoices = db.get_all_invoices()
    return [
        {
            "id": inv.id,
            "invoice_number": inv.invoice_number,
            "vendor_name": inv.vendor_name,
            "total": inv.total,
            "currency": inv.currency,
            "created_at": inv.created_at.isoformat(),
        }
        for inv in invoices
    ]


@app.get("/invoices/vendor-summary")
def vendor_summary(current_user=Depends(get_current_user)):
    db = DatabaseManager()
    return db.get_vendor_summary()


@app.get("/health")
def health():
    return {"status": "ok", "service": "FinSentinelAI"}
