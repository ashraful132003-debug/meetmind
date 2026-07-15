"""FastAPI application assembly: middleware, security headers, error handling."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .config import settings
from .db import engine, init_models
from .routers import analytics, auth, chat, email, meetings
from .schemas import HealthResponse
from .services.llm import health as llm_health

VERSION = "1.0.0"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("meetmind")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_models()
    log.info("MeetMind %s starting — env=%s, llm=%s", VERSION, settings.app_env, settings.llm_provider)
    if settings.is_production and settings.frontend_origin.startswith("http://"):
        log.warning("APP_ENV=production but FRONTEND_ORIGIN is not HTTPS. Cookies will not be secure.")
    yield
    await engine.dispose()


app = FastAPI(
    title="MeetMind API",
    version=VERSION,
    lifespan=lifespan,
    # Interactive docs are a development convenience, not something to expose
    # on a public deployment.
    docs_url=None if settings.is_production else "/api/docs",
    redoc_url=None,
    openapi_url=None if settings.is_production else "/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,  # explicit list — never "*" with credentials
    allow_credentials=True,               # needed for the refresh cookie
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)


@app.middleware("http")
async def security_and_logging(request: Request, call_next):
    request_id = uuid.uuid4().hex[:12]
    started = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        # Log the detail; return a generic message. Stack traces and exception
        # text are internal information — they don't belong in an HTTP response.
        log.exception("Unhandled error [%s] %s %s", request_id, request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Something went wrong on our side.", "request_id": request_id},
        )

    elapsed_ms = (time.perf_counter() - started) * 1000

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=(self)"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    # The API only ever returns JSON, media, or the sandboxed email preview —
    # so it can afford the strictest possible CSP.
    response.headers.setdefault(
        "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    )
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    if elapsed_ms > 1000:
        log.info("%s %s -> %s (%.0fms)", request.method, request.url.path, response.status_code, elapsed_ms)
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Turn Pydantic's nested error structure into one readable sentence —
    the frontend shows this text directly to the user."""
    messages = []
    for err in exc.errors():
        field = ".".join(str(p) for p in err.get("loc", []) if p not in ("body", "query"))
        msg = err.get("msg", "is invalid")
        msg = msg.removeprefix("Value error, ")
        messages.append(f"{field}: {msg}" if field else msg)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": " · ".join(messages) or "The request was invalid."},
    )


app.include_router(auth.router)
app.include_router(meetings.router)
app.include_router(chat.router)
app.include_router(analytics.router)
app.include_router(email.router)


@app.get("/api/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    """Real health, not a hardcoded 200. The UI uses this to tell the user
    exactly what is wrong when something is down."""
    db_ok = True
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as e:
        log.warning("Database health check failed: %s", e)
        db_ok = False

    llm = await llm_health()
    healthy = db_ok and llm.get("reachable") and not llm.get("detail")

    return HealthResponse(
        status="healthy" if healthy else "degraded",
        database=db_ok,
        llm=llm,
        whisper_model=settings.whisper_model,
        version=VERSION,
    )
