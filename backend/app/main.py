"""FastAPI application assembly: middleware, security headers, error handling."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .config import BASE_DIR, settings
from .db import engine, init_models
from .routers import analytics, auth, chat, email, meetings
from .schemas import HealthResponse
from .services.llm import health as llm_health

VERSION = "1.0.0"

# Nothing may load anything. Correct for JSON and media responses.
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"

# What the SPA actually needs, and not one directive more:
#   script-src 'self'        - our bundle only. NOT 'unsafe-inline': an injected
#                              <script> must never execute, which is the whole
#                              point of having a CSP on a page that renders
#                              user-supplied meeting text.
#   style-src 'unsafe-inline'- React's style={{...}} prop emits inline styles.
#                              Unavoidable without a nonce pipeline; inline CSS is
#                              a far smaller risk than inline JS.
#   connect-src 'self'       - the frontend is forbidden from talking to any third
#                              party. This enforces the privacy claim in the
#                              browser itself rather than on trust.
#   media-src 'self' blob:   - blob: is needed for the recorder's local playback.
SPA_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data:; "
    "media-src 'self' blob:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'none'; "
    "form-action 'self'"
)

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

    # Two different policies, because this app serves two different things.
    #
    # The API returns JSON, media, or the sandboxed email preview, so it gets the
    # strictest possible policy: load nothing, ever.
    #
    # The SPA cannot live under that policy - `default-src 'none'` blocks its own
    # JavaScript and CSS, and the page renders completely blank with no error
    # anywhere except the browser console. curl does not enforce CSP, so this is
    # invisible to every command-line check; it only appears in a real browser,
    # in production. Hence the split.
    if not response.headers.get("Content-Security-Policy"):
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("text/html"):
            response.headers["Content-Security-Policy"] = SPA_CSP
        else:
            response.headers["Content-Security-Policy"] = API_CSP
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


def _mount_spa() -> None:
    """Serve the built frontend from this same app, when it exists.

    In development the SPA is served by Vite on :5173 and proxied here, so this
    does nothing. In production (one Docker image, one free instance) the built
    assets sit in ./static and FastAPI serves them.

    Same-origin is the point, not a convenience: it means no CORS at all, and the
    refresh cookie stays SameSite=Lax without any cross-site exemption. A
    two-service deployment would need both, and would burn a second free instance.
    """
    static_dir = BASE_DIR / "static"
    index = static_dir / "index.html"
    if not index.exists():
        log.info("No built frontend at %s — API-only mode (fine in development)", static_dir)
        return

    assets = static_dir / "assets"
    if assets.is_dir():
        # Hashed filenames are content-addressed, so they can be cached forever.
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> Response:
        # Never let an unknown /api/* path fall through to index.html - that would
        # turn a typo'd endpoint into a confusing 200 with HTML in it.
        if full_path.startswith("api/"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

        candidate = (static_dir / full_path).resolve()
        # Path traversal guard: only serve files genuinely inside static_dir.
        if (
            full_path
            and candidate.is_file()
            and candidate.is_relative_to(static_dir.resolve())
        ):
            return FileResponse(candidate)

        # Everything else is a client-side route; React Router will handle it.
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    log.info("Serving the built frontend from %s", static_dir)


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


# MUST be last. The SPA handler registers a catch-all GET /{full_path:path}, and
# FastAPI matches routes in definition order - mounting it any earlier would
# shadow every API route defined after it.
_mount_spa()
