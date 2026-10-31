from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from api.routes.auth import get_current_user
from api.dependencies import get_pipeline
from core.uploads import save_upload
from models.user import User
from config import get_settings
from security.files import contained_path

router = APIRouter()


class DocumentResponse(BaseModel):
    filename: str
    status: str
    message: str | None = None


@router.post("/upload", response_model=list[DocumentResponse])
async def upload_documents(files: list[UploadFile] = File(...),
                           current_user: User = Depends(get_current_user), pipeline=Depends(get_pipeline)):
    settings = get_settings()
    if len(files) > settings.max_upload_files:
        raise HTTPException(status_code=413, detail="Too many files")
    directory = settings.data_dir / "uploads" / str(current_user.id)
    session = f"user_{current_user.id}_default"
    responses = []
    for upload in files:
        try:
            path = await save_upload(upload, directory, settings.max_upload_bytes)
            result = await run_in_threadpool(pipeline.ingest_and_store, path, session, current_user.id)
            errors = [item for item in result["documents"] if item["status"] == "error"]
            if errors:
                responses.append(DocumentResponse(filename=path.name, status="error", message="Processing failed; remove and retry"))
            else:
                responses.append(DocumentResponse(filename=path.name, status="success", message="Indexed locally"))
        except FileExistsError:
            responses.append(DocumentResponse(filename=upload.filename or "", status="error", message="Filename exists; delete it before replacing"))
        except (ValueError, UnicodeError) as exc:
            responses.append(DocumentResponse(filename=upload.filename or "", status="error", message=str(exc)))
        finally:
            await upload.close()
    return responses


@router.get("/list")
def list_documents(current_user: User = Depends(get_current_user), pipeline=Depends(get_pipeline)):
    session = f"user_{current_user.id}_default"
    results = pipeline.vector_store.collection.get(where={"session_id": session}, include=["metadatas"])
    return {"documents": sorted({m["file_name"] for m in results.get("metadatas", []) if m and "file_name" in m})}


@router.delete("/{filename}")
def delete_document(filename: str, current_user: User = Depends(get_current_user), pipeline=Depends(get_pipeline)):
    try:
        path = contained_path(get_settings().data_dir / "uploads" / str(current_user.id), filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    pipeline.vector_store.delete_by_filter({"session_id": f"user_{current_user.id}_default", "file_name": filename})
    path.unlink(missing_ok=True)
    return {"status": "success"}
