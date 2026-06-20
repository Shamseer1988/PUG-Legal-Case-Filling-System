"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app import __version__
from app.api.v1 import api_router
from app.core import request_context
from app.core.config import settings
from app.core.hardening import SecurityHeadersMiddleware
from app.core.logging import setup_logging


def _maybe_init_sentry() -> None:
    if not settings.sentry_dsn:
        return
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            release=f"pug-legal@{__version__}",
            environment=settings.app_env,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            send_default_pii=False,
        )
        logger.info("Sentry initialised")
    except Exception as e:  # pragma: no cover
        logger.warning("Sentry init failed: {}", e)


def _compute_cors_config() -> tuple[list[str], bool]:
    """Resolve CORS allow_origins, supporting ``*`` as wildcard and
    auto-including common localhost variants outside production so
    login works whether the user opens 127.0.0.1, localhost or [::1]."""
    raw = settings.cors_origins_list
    if any(o == "*" for o in raw):
        return ["*"], True
    origins = list(raw)
    if settings.app_env != "production":
        for extra in (
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://[::1]:3000",
        ):
            if extra not in origins:
                origins.append(extra)
    return origins, False


_CORS_ORIGINS, _CORS_WILDCARD = _compute_cors_config()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    _maybe_init_sentry()
    settings.storage_path.mkdir(parents=True, exist_ok=True)
    settings.backup_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"{settings.app_name} starting (env={settings.app_env}, v={__version__})")
    if _CORS_WILDCARD:
        logger.info("CORS: wildcard mode (any origin allowed, credentials disabled)")
    else:
        logger.info("CORS: allow_origins={}", _CORS_ORIGINS)
    # Background scheduler for scheduled reports (Phase 7)
    from app.services import scheduler_service

    scheduler_service.start()
    try:
        yield
    finally:
        scheduler_service.stop()
        logger.info(f"{settings.app_name} shutting down")


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    debug=settings.app_debug,
    lifespan=lifespan,
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    # Browsers reject Access-Control-Allow-Credentials=true together with
    # Allow-Origin=*, so disable credentials in wildcard mode.
    allow_credentials=not _CORS_WILDCARD,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    """Populate a per-request context (IP + User-Agent) consumed by the audit log."""
    client_host = request.client.host if request.client else ""
    # Trust X-Forwarded-For only if it's set (typical when behind nginx)
    fwd = request.headers.get("x-forwarded-for", "")
    ip = (fwd.split(",")[0].strip() if fwd else client_host)[:45]
    ua = request.headers.get("user-agent", "")[:500]
    ctx = request_context.RequestContext(ip=ip, user_agent=ua)
    token = request_context.set_ctx(ctx)
    try:
        return await call_next(request)
    finally:
        request_context.reset_ctx(token)


app.include_router(api_router, prefix="/api/v1")


@app.get("/")
def root() -> dict:
    return {
        "app": settings.app_name,
        "version": __version__,
        "docs": "/docs",
        "health": "/api/v1/health",
    }
