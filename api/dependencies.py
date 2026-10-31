"""Application-scoped resources; importing routes never loads models."""
from threading import Lock

from fastapi import Request

from database.db_manager import DatabaseManager


class AppContainer:
    def __init__(self, pipeline=None):
        self.db = DatabaseManager()
        self.pipeline = pipeline
        self.lock = Lock()

    def get_pipeline(self):
        with self.lock:
            if self.pipeline is None:
                from core.pipeline import FinSentinelPipeline

                self.pipeline = FinSentinelPipeline(db_manager=self.db)
            return self.pipeline


def get_db(request: Request):
    return request.app.state.container.db


def get_pipeline(request: Request):
    return request.app.state.container.get_pipeline()
