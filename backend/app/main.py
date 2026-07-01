from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal, Base, engine
from app.core.logging import configure_logging, get_logger
from app.core.rate_limit import rate_limit_middleware
from app.core.redis_client import redis_client
from app.services.glossary_seed import load_seed_glossaries
from app.services.llm_service import get_llm_client
from app.services.storage_service import get_storage
from app.workers.scheduler import start_scheduler, stop_scheduler


settings = get_settings()
configure_logging(settings.log_level, settings.app_env)
logger = get_logger(__name__)


async def _ensure_tables() -> None:
    from app.models import glossary, order, quota, task, user

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, checkfirst=True)


async def _bootstrap_seed_glossaries() -> None:
    try:
        async with AsyncSessionLocal() as session:
            result = await load_seed_glossaries(session)
            logger.info(
                "seed.glossaries.loaded",
                inserted=result.inserted,
                updated=result.updated,
                skipped_existing=result.skipped_existing,
                total_terms=result.total_terms,
                files=len(result.files),
            )
    except Exception as exc:
        logger.error("seed.bootstrap_failed", error=str(exc))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info(
        "application.startup",
        env=settings.app_env,
        version=settings.app_version,
    )

    try:
        await _ensure_tables()
        logger.info("database.ready", url=_mask_url(settings.database_url))
    except Exception as exc:
        logger.error("database.connection_failed", error=str(exc))

    try:
        await _bootstrap_seed_glossaries()
    except Exception as exc:
        logger.error("seed.bootstrap_failed", error=str(exc))

    try:
        from app.services.task_service import reap_stale_processing_tasks

        async with AsyncSessionLocal() as session:
            reaped = await reap_stale_processing_tasks(session, older_than_seconds=600)
        if reaped:
            logger.warning("tasks.stale_processing.reaped", count=reaped)
        else:
            logger.info("tasks.stale_processing.none")
    except Exception as exc:
        logger.warning("tasks.stale_processing.failed", error=str(exc))

    try:
        await redis_client.ping()
        logger.info("redis.connected", url=_mask_url(settings.redis_url))
    except Exception as exc:
        logger.error("redis.connection_failed", error=str(exc))

    try:
        backend = get_storage()
        logger.info(
            "storage.initialized",
            backend=type(backend).__name__,
        )
    except Exception as exc:
        logger.error("storage.init_failed", error=str(exc))

    try:
        for svc in ("deepseek", "glm", "openai"):
            try:
                get_llm_client(svc)  # type: ignore[arg-type]
            except Exception as exc:
                logger.warning(
                    "llm.client.init_failed",
                    service=svc,
                    error=str(exc),
                )
    except Exception as exc:
        logger.error("llm.clients.init_failed", error=str(exc))

    try:
        start_scheduler(background=True)
        logger.info("scheduler.started")
    except Exception as exc:
        logger.error("scheduler.start_failed", error=str(exc))

    yield

    logger.info("application.shutdown.begin")
    try:
        stop_scheduler()
    except Exception as exc:
        logger.warning("scheduler.stop_failed", error=str(exc))

    try:
        await engine.dispose()
        logger.info("database.disposed")
    except Exception as exc:
        logger.warning("database.dispose_failed", error=str(exc))

    try:
        await redis_client.aclose()
        logger.info("redis.closed")
    except Exception as exc:
        logger.warning("redis.close_failed", error=str(exc))

    logger.info("application.shutdown.complete")


def _mask_url(url: str) -> str:
    if "@" not in url:
        return url
    scheme, rest = url.split("://", 1)
    creds, host = rest.split("@", 1)
    if ":" in creds:
        user, _ = creds.split(":", 1)
        return f"{scheme}://{user}:**@{host}"
    return f"{scheme}://{creds}@{host}"


app = FastAPI(
    title="Paper Translate API",
    version="0.1.0",
    description="Backend API for academic paper PDF translation SaaS",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.middleware("http")(rate_limit_middleware)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "unhandled.exception",
        path=request.url.path,
        method=request.method,
        error_type=type(exc).__name__,
        error=str(exc),
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error_type": type(exc).__name__,
            "path": request.url.path,
        },
    )


app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/api/v1/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/v1/storage/local/{key:path}", tags=["storage"])
async def local_storage_download(
    key: str,
    token: str | None = Query(default=None),
    exp: int | None = Query(default=None),
) -> FileResponse:
    from app.services.storage_service import get_storage as _gs

    backend = _gs()
    if not hasattr(backend, "verify_signed_token"):
        raise HTTPException(
            status_code=404,
            detail={"code": "not_supported"},
        )
    if not token or not exp:
        raise HTTPException(
            status_code=403,
            detail={"code": "missing_signature"},
        )
    if int(exp) < __import__("time").time():
        raise HTTPException(
            status_code=410,
            detail={"code": "expired"},
        )
    if not backend.verify_signed_token(key, token):  # type: ignore[attr-defined]
        raise HTTPException(
            status_code=403,
            detail={"code": "invalid_signature"},
        )
    from app.services.storage_service import LocalStorage

    if not isinstance(backend, LocalStorage):
        raise HTTPException(status_code=404, detail={"code": "not_local"})
    path = backend._resolve_path(key)  # type: ignore[attr-defined]
    if not path.is_file():
        raise HTTPException(status_code=404, detail={"code": "object_not_found"})
    return FileResponse(str(path), filename=path.name)