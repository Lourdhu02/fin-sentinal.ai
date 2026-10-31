import os

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from api.routes.auth import get_current_user
from config import get_settings
from core.hardware import hardware_inventory

router = APIRouter()


@router.get("/system/capabilities")
def capabilities(user=Depends(get_current_user)):
    return {**hardware_inventory(), "offline_models": get_settings().offline,
            "inference_backend": os.getenv("FINSENTINEL_INFERENCE", "ollama"),
            "embedding_device": "cpu", "gpu_scheduling": "serialized"}


@router.get("/health/ready")
def ready(request: Request, user=Depends(get_current_user)):
    pipeline = request.app.state.container.pipeline
    initialized = pipeline is not None
    return JSONResponse({"models_initialized": initialized,
                         "generation_connectivity": "not_probed",
                         "status": "initialized" if initialized else "cold"},
                        status_code=200 if initialized else 503)
