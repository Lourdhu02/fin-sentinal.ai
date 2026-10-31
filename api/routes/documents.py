import re
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from pathlib import Path, PurePosixPath

from api.routes.auth import get_current_user
from models.user import User
from api.dependencies import get_pipeline
from config import get_settings
from security.files import safe_filename, contained_path

router = APIRouter()

def _sanitize_filename(filename: str) -> str:
    """Strip path components and dangerous characters to prevent path traversal."""
    # Extract just the filename, discarding any directory components
    return safe_filename(filename)
    # Remove any remaining problematic characters
    name = re.sub(r'[^\w\s\-.]', '_', name).strip()
    return name or "unnamed_file"

class DocumentResponse(BaseModel):
    filename: str
    status: str
    message: str | None = None

@router.post("/upload", response_model=list[DocumentResponse])
async def upload_documents(
    files: list[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    pipeline=Depends(get_pipeline),
):
    settings = get_settings()
    upload_dir = settings.data_dir / "uploads" / str(current_user.id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # We use user_id as the session_id to isolate data per user in ChromaDB
    # Or we can allow the frontend to pass a session_id. For now, let's tie to user_id.
    session_id = f"user_{current_user.id}_default"
    
    responses = []
    for file in files:
        safe_name = _sanitize_filename(file.filename)
        file_path = contained_path(upload_dir, safe_name)
        with open(file_path, "wb") as f:
            f.write(await file.read())
            
        try:
            result = pipeline.ingest_and_store(file_path, session_id=session_id, user_id=current_user.id)
            errors = [d for d in result.get("documents", []) if d.get("status") == "error"]
            if errors:
                responses.append(DocumentResponse(filename=safe_name, status="error", message=errors[0].get("error")))
            else:
                responses.append(DocumentResponse(filename=safe_name, status="success", message="Indexed into ChromaDB"))
        except Exception as e:
            responses.append(DocumentResponse(filename=safe_name, status="error", message=str(e)))
            
    return responses

@router.get("/list")
def list_documents(current_user: User = Depends(get_current_user), pipeline=Depends(get_pipeline)):
    # Query ChromaDB for distinct filenames for this user
    session_id = f"user_{current_user.id}_default"
    try:
        # We can do a dummy search to get metadata, or access collection directly
        results = pipeline.vector_store.collection.get(
            where={"session_id": session_id},
            include=["metadatas"]
        )
        filenames = set()
        if results and results.get("metadatas"):
            for meta in results["metadatas"]:
                if meta and "file_name" in meta:
                    filenames.add(meta["file_name"])
        return {"documents": list(filenames)}
    except Exception as e:
        return {"documents": []}

@router.delete("/{filename}")
def delete_document(filename: str, current_user: User = Depends(get_current_user), pipeline=Depends(get_pipeline)):
    settings = get_settings()
    try:
        file_path = contained_path(settings.data_dir / "uploads" / str(current_user.id), filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    session_id = f"user_{current_user.id}_default"
    try:
        pipeline.vector_store.delete_by_filter({
            "session_id": session_id,
            "file_name": filename
        })
        
        # Also delete physical file
        if file_path.exists():
            file_path.unlink()
            
        return {"status": "success", "message": f"Deleted {filename}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
