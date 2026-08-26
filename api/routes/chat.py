from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Any

from api.routes.auth import get_current_user
from models.user import User
from core.pipeline import FinSentinelPipeline

router = APIRouter()
pipeline = FinSentinelPipeline()

class ChatRequest(BaseModel):
    query: str

class ChatResponse(BaseModel):
    query: str
    response: str
    sources: list[dict[str, Any]]

@router.post("/", response_model=ChatResponse)
def chat_with_documents(request: ChatRequest, current_user: User = Depends(get_current_user)):
    session_id = f"user_{current_user.id}_default"
    
    try:
        result = pipeline.query(request.query, session_id=session_id, user_id=current_user.id)
        
        # Clean up sources for frontend
        sources = []
        for r in result.get("results", []):
            sources.append({
                "file_name": r.get("file_name", "Unknown"),
                "score": r.get("score", 0.0),
                "text": r.get("text", "")[:300] + "..."
            })
            
        return ChatResponse(
            query=request.query,
            response=result.get("response", "Error generating response"),
            sources=sources
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/reset")
def reset_chat(current_user: User = Depends(get_current_user)):
    session_id = f"user_{current_user.id}_default"
    cleared = pipeline.reset_conversation(session_id)
    return {
        "status": "success",
        "message": f"Cleared {cleared} turns for session {session_id}",
    }
