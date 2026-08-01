from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from invoice_pipeline.api.limiter import limiter
from invoice_pipeline.api.routes import (
    batch,
    dashboard,
    documents,
    export,
    invoices,
    projects,
    providers,
    review,
    session,
    vendors,
    workspaces,
)
from invoice_pipeline.api.routes import settings as settings_route
from invoice_pipeline.config import settings
from invoice_pipeline.llm.base import NoLLMProviderConfigured
from invoice_pipeline.llm.factory import create_provider
from invoice_pipeline.schemas import HealthResponse, LLMStatusResponse, ProblemDetail
from invoice_pipeline.services.workspace_cleanup import run_cleanup

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    log.info("startup", app=settings.APP_NAME, env=settings.APP_ENV)
    try:
        provider = await create_provider()
        provider_name = getattr(provider, "provider_name", "unknown")

        # Safely resolve model and endpoint strings to prevent None validation issues
        model = (
            getattr(provider, "_model", None)
            or getattr(settings, f"{provider_name.upper()}_MODEL", None)
            or "unknown"
        )

        endpoint = (
            getattr(provider, "_base_url", None)
            or getattr(getattr(provider, "_openai_client", None), "base_url", None)
            or getattr(getattr(provider, "_client", None), "base_url", None)
            or None
        )

        app.state.llm_provider = provider
        app.state.llm_status = {
            "provider": provider_name,
            "model": str(model),
            "endpoint": str(endpoint) if endpoint else None,
        }
    except NoLLMProviderConfigured as exc:
        log.warning("llm_provider_not_configured", error=str(exc))
        app.state.llm_provider = None
        app.state.llm_status = {"provider": "none", "model": "none", "endpoint": None}

    from invoice_pipeline.canonicalizers.qdrant_client import ensure_qdrant_collection

    await ensure_qdrant_collection()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(run_cleanup, "interval", hours=1, id="workspace_cleanup")
    scheduler.start()
    app.state.scheduler = scheduler
    yield
    scheduler.shutdown()


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router, prefix="/documents", tags=["documents"])
app.include_router(invoices.router, prefix="/invoices", tags=["invoices"])
app.include_router(projects.router, prefix="/projects", tags=["projects"])
app.include_router(review.router, prefix="/review", tags=["review"])
app.include_router(vendors.router, prefix="/vendors", tags=["vendors"])
app.include_router(settings_route.router, prefix="/settings", tags=["settings"])
app.include_router(providers.router, prefix="/providers", tags=["providers"])
app.include_router(batch.router, prefix="/batch", tags=["batch"])
app.include_router(export.router, prefix="/export", tags=["export"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
app.include_router(workspaces.router, prefix="/workspaces", tags=["workspaces"])
app.include_router(session.router, prefix="/session", tags=["session"])


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.error("unhandled_exception", path=request.url.path, error=str(exc))
    problem = ProblemDetail(
        title="Internal Server Error",
        status=500,
        detail=str(exc) if settings.DEBUG else "An unexpected error occurred.",
        instance=str(request.url),
    )
    return JSONResponse(status_code=500, content=problem.model_dump())


@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version="0.1.0")


@app.get("/metrics", tags=["system"], response_class=PlainTextResponse)
async def metrics() -> PlainTextResponse:
    return PlainTextResponse(
        generate_latest().decode("utf-8"),
        media_type=CONTENT_TYPE_LATEST,
    )


@app.get("/llm/status", response_model=LLMStatusResponse, tags=["system"])
async def llm_status() -> LLMStatusResponse:
    try:
        from invoice_pipeline.llm.factory import get_provider

        provider = await get_provider()
        provider_name = getattr(provider, "provider_name", "unknown")

        from invoice_pipeline.config import settings

        model = "unknown"
        if provider_name == "lm_studio":
            from invoice_pipeline.llm.lm_studio import _get_active_models

            active_models = await _get_active_models()
            if active_models:
                if settings.LM_STUDIO_MODEL in active_models:
                    model = settings.LM_STUDIO_MODEL
                else:
                    model = active_models[0]
            else:
                model = settings.LM_STUDIO_MODEL or "none"
        elif provider_name == "llamacpp":
            model = getattr(provider, "_model", None) or settings.LLAMACPP_MODEL or "local-model"
        else:
            model = (
                getattr(provider, "_model", None)
                or getattr(settings, f"{provider_name.upper()}_MODEL", None)
                or "unknown"
            )

        endpoint = (
            getattr(provider, "_base_url", None)
            or getattr(getattr(provider, "_openai_client", None), "base_url", None)
            or getattr(getattr(provider, "_client", None), "base_url", None)
            or None
        )

        status = {
            "provider": provider_name,
            "model": str(model),
            "endpoint": str(endpoint) if endpoint else None,
        }
        app.state.llm_status = status
    except Exception as exc:
        log.warning("llm_status_dynamic_error", error=str(exc))
        status = getattr(
            app.state, "llm_status", {"provider": "none", "model": "none", "endpoint": None}
        )
    return LLMStatusResponse(**status)


if __name__ == "__main__":
    uvicorn.run("invoice_pipeline.api.main:app", host="0.0.0.0", port=8000, reload=True)
