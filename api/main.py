from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

    @app.get("/api/health")
    def health():
        return {"status": "healthy"}

    return app


app = create_app()
