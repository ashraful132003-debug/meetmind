# Single-image build for free-tier hosting: React SPA + FastAPI in one container.
#
# Why one image rather than the two in docker-compose.yml:
#   * A free plan gives you one instance. Two services = two instances.
#   * Same-origin means no CORS and the refresh cookie stays SameSite=Lax with no
#     cross-site exemption. Splitting them would need both.
#
# This image deliberately does NOT include Whisper or Llama weights. They need
# ~5GB of RAM; a free instance has 512MB. Deployed mode calls Groq's free tier
# instead (see DEPLOY.md). Diarization still runs here - it is a 25MB ONNX model.

# --- Stage 1: build the SPA --------------------------------------------------
FROM node:20-alpine AS frontend

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


# --- Stage 2: build python wheels --------------------------------------------
FROM python:3.12-slim AS wheels

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY backend/requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt


# --- Stage 3: runtime --------------------------------------------------------
FROM python:3.12-slim AS runtime

# ffmpeg is a real dependency: pydub shells out to it to decode anything that is
# not plain PCM wav (m4a, mp4, and the webm the browser recorder produces).
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root: if the app is ever compromised, the attacker lands as a user who
# cannot write to the application code.
RUN useradd --create-home --shell /usr/sbin/nologin --uid 1000 meetmind

WORKDIR /app

COPY --from=wheels /wheels /wheels
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

COPY --chown=meetmind:meetmind backend/app ./app
COPY --from=frontend --chown=meetmind:meetmind /build/dist ./static

RUN mkdir -p /app/storage/media /app/outbox \
    && chown -R meetmind:meetmind /app/storage /app/outbox

# Speaker model for diarization: WeSpeaker ResNet34-LM (25MB, Apache-2.0, no
# account). Baked in so the container starts offline and deterministically.
#
# It lives in /app/models, NOT /app/storage/models: compose mounts a volume over
# /app/storage, which would shadow it, and the app would silently fall back to
# hand-built features - 79.5% against this model's 94.0% - with nothing in the
# logs of an apparently healthy container to explain why.
ADD --chown=meetmind:meetmind \
    https://huggingface.co/onnx-community/wespeaker-voxceleb-resnet34-LM/resolve/main/onnx/model.onnx \
    /app/models/wespeaker.onnx
RUN test -s /app/models/wespeaker.onnx || (echo "speaker model download failed" && exit 1)

USER meetmind

# APP_BASE_DIR is load-bearing, not cosmetic. Without it, config.py infers the
# base directory from its own location - which is /app/app/config.py here, giving
# "/" - and the app would try to write /storage/media as a non-root user. It
# would deploy green and then die on the first upload.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_BASE_DIR=/app \
    SPEAKER_MODEL_PATH=/app/models/wespeaker.onnx \
    PORT=8000

EXPOSE 8000

# Hits the real health endpoint, which genuinely checks the database and the LLM,
# so an unhealthy container reports unhealthy rather than merely "up".
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/api/health" || exit 1

# Render (and most PaaS) inject $PORT and expect the app to bind it.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
