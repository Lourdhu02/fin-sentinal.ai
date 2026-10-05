import re
import uuid
import magic
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from pathlib import Path, PurePosixPath

from api.routes.auth import get_current_user
from models.user import User
from core.pipeline import FinSentinelPipeline
from config import get_settings
from api.deps import get_pipeline

router = APIRouter()
settings = get_settings()

ALLOWED_MIME_TYPES = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/tiff": ".tiff",
    "text/csv": ".csv",
    "application/json": ".json",
    "text/markdown": ".md",
    "text/html": ".html"
}

def _sanitize_filename(filename: str) -> str:
    name = PurePosixPath(filename).name or Path(filename).name
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
    pipeline: FinSentinelPipeline = Depends(get_pipeline)
):
    upload_dir = settings.data_dir / "uploads" / str(current_user.id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    session_id = f"user_{current_user.id}_default"
    
    responses = []
    for file in files:
        safe_name = _sanitize_filename(file.filename)
        unique_name = f"{uuid.uuid4().hex}_{safe_name}"
        file_path = upload_dir / unique_name
        
        try:
            bytes_written = 0
            mime = magic.Magic(mime=True)
            detected_mime = None
            
            with open(file_path, "wb") as f:
                while True:
                    chunk = await file.read(1024 * 1024)  # 1MB chunks
                    if not chunk:
                        break
                    
                    if bytes_written == 0:
                        detected_mime = mime.from_buffer(chunk)
                    
                    bytes_written += len(chunk)
                    if bytes_written > settings.max_upload_size:
                        raise HTTPException(status_code=413, detail=f"File {safe_name} exceeds max size")
                    
                    f.write(chunk)
            
            if detected_mime not in ALLOWED_MIME_TYPES:
                file_path.unlink()
                raise HTTPException(status_code=400, detail=f"Invalid file type {detected_mime}")
            
            # For JSON/text the magic buffer might differ but we do basic check
            
            result = pipeline.ingest_and_store(file_path, session_id=session_id, user_id=current_user.id)
            errors = [d for d in result.get("documents", []) if d.get("status") == "error"]
            if errors:
                responses.append(DocumentResponse(filename=safe_name, status="error", message="Failed to index"))
            else:
                responses.append(DocumentResponse(filename=safe_name, status="success", message="Indexed into ChromaDB"))
        except HTTPException as he:
            responses.append(DocumentResponse(filename=safe_name, status="error", message=he.detail))
            if file_path.exists():
                file_path.unlink()
        except Exception as e:
            responses.append(DocumentResponse(filename=safe_name, status="error", message="Internal error during upload"))
            if file_path.exists():
                file_path.unlink()
            
    return responses

@router.get("/list")
def list_documents(
    current_user: User = Depends(get_current_user),
    pipeline: FinSentinelPipeline = Depends(get_pipeline)
):
    session_id = f"user_{current_user.id}_default"
    try:
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
def delete_document(
    filename: str,
    current_user: User = Depends(get_current_user),
    pipeline: FinSentinelPipeline = Depends(get_pipeline)
):
    session_id = f"user_{current_user.id}_default"
    safe_name = _sanitize_filename(filename)
    
    upload_dir = settings.data_dir / "uploads" / str(current_user.id)
    upload_dir = upload_dir.resolve()
    
    # Needs to match exactly or resolve to inside
    file_path = (upload_dir / safe_name).resolve()
    if not str(file_path).startswith(str(upload_dir)):
        raise HTTPException(status_code=400, detail="Invalid file path")
        
    try:
        pipeline.vector_store.delete_by_filter({
            "session_id": session_id,
            "file_name": safe_name
        })
        
        if file_path.exists():
            file_path.unlink()
            
        return {"status": "success", "message": "Deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to delete document")
