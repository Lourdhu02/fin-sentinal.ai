from contextlib import asynccontextmanager
import os
import logging
import time
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.dependencies import AppContainer
from config import get_settings


def create_app(pipeline=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        get_settings()
        app.state.container = AppContainer(pipeline=pipeline)
        yield
        app.state.container.db.close()

    app = FastAPI(title="FinSentinelAI API", version="1.1.0", lifespan=lifespan)
    origins = os.getenv("FINSENTINEL_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in origins.split(",")],
                       allow_credentials=True, allow_methods=["GET", "POST", "DELETE"],
                       allow_headers=["Authorization", "Content-Type"])
    from api.routes import auth, chat, documents

    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
    app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
    from api.system import router as system_router
    app.include_router(system_router, prefix="/api", tags=["system"])

    @app.exception_handler(RuntimeError)
    async def runtime_error(request, exc):
        logging.getLogger("finsentinel").error("service_failure type=%s", type(exc).__name__)
        return JSONResponse({"detail": "Local service unavailable; inspect local diagnostics"}, status_code=503)

    @app.middleware("http")
    async def request_timing(request, call_next):
        request_id = uuid.uuid4().hex
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        route = request.scope.get("route")
        logging.getLogger("finsentinel").info("request id=%s route=%s status=%s elapsed_ms=%.1f",
            request_id, getattr(route, "path", "unmatched"), response.status_code,
            (time.perf_counter() - start) * 1000)
        return response

    @app.get("/api/health")
    def health():
        return {"status": "healthy"}

    return app


app = create_app()
