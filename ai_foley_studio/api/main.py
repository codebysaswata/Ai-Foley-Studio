"""FastAPI application factory for the standalone local backend."""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ai_foley_studio.api.errors import ApiError
from ai_foley_studio.api.manager import JobManager
from ai_foley_studio.api.routes import router
from ai_foley_studio.api.schemas import ApiErrorBody, HealthResponse, ReadinessResponse
from ai_foley_studio.api.settings import ApiSettings

log = logging.getLogger("ai_foley_studio.api")


def create_app(settings: ApiSettings | None = None, *, manager: JobManager | None = None) -> FastAPI:
    config = settings or ApiSettings.from_env()
    runtime = manager or JobManager(config)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await runtime.start()
        try:
            yield
        finally:
            await runtime.stop()

    app = FastAPI(
        title="AI Foley Studio API", version="1.0.0",
        description="Authenticated local HTTP service for asynchronous, chunk-based Foley generation.",
        lifespan=lifespan,
    )
    app.state.runtime = runtime
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.cors_origins), allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID"],
        expose_headers=["Content-Disposition", "X-Request-ID"],
    )

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        supplied = request.headers.get("x-request-id", "")
        request_id_value = supplied[:80] if supplied and all(ch.isalnum() or ch in "-_." for ch in supplied[:80]) else str(uuid.uuid4())
        request.state.request_id = request_id_value
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id_value
        return response

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": ApiErrorBody(code=exc.code, message=exc.message, request_id=getattr(request.state, "request_id", None)).model_dump()},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"error": ApiErrorBody(
            code="INVALID_REQUEST", message="Request fields are missing or outside supported limits.",
            request_id=getattr(request.state, "request_id", None),
        ).model_dump()})

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        log.exception("event=http_request_failed request_id=%s", getattr(request.state, "request_id", "unknown"))
        return JSONResponse(status_code=500, content={"error": ApiErrorBody(
            code="INTERNAL_SERVER_ERROR", message="The request failed unexpectedly.",
            request_id=getattr(request.state, "request_id", None),
        ).model_dump()})

    @app.get("/health/live", response_model=HealthResponse, tags=["health"])
    async def live() -> HealthResponse:
        return HealthResponse(status="alive")

    @app.get("/health/ready", response_model=ReadinessResponse, tags=["health"], responses={503: {"model": ReadinessResponse}})
    async def ready() -> JSONResponse:
        is_ready, checks = runtime.readiness()
        payload = ReadinessResponse(status="ready" if is_ready else "not_ready", checks=checks)
        return JSONResponse(status_code=200 if is_ready else 503, content=payload.model_dump())

    app.include_router(router)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = ApiSettings.from_env()
    uvicorn.run("ai_foley_studio.api.main:app", host=settings.host, port=settings.port, workers=1)
