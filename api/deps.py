from fastapi import Request

from core.pipeline import FinSentinelPipeline

def get_pipeline(request: Request) -> FinSentinelPipeline:
    return request.app.state.pipeline
