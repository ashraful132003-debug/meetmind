# Multi-stage build for the MeetMind API.
#
# Stage 1 compiles wheels (argon2-cffi and cryptography need a toolchain), stage 2
# copies only the built artefacts. The runtime image never contains gcc, so a
# remote-code-execution bug has nothing to compile with.

FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt


FROM python:3.12-slim AS runtime

# ffmpeg is a real runtime dependency: pydub shells out to it for any audio
# container that isn't plain PCM WAV (m4a, mp4, webm from browser recordings).
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Run as a non-root user. If the app is ever compromised, the attacker lands as
# a user who cannot write to the application code.
RUN useradd --create-home --shell /usr/sbin/nologin --uid 1000 meetmind

WORKDIR /app

COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

COPY --chown=meetmind:meetmind ./app ./app

# Storage is a volume mount, but create it with the right owner so a fresh run
# without an explicit volume still works.
RUN mkdir -p /app/storage/media /app/storage/models /app/outbox \
    && chown -R meetmind:meetmind /app/storage /app/outbox

# Speaker-recognition model for diarization: WeSpeaker ResNet34-LM (25MB,
# Apache-2.0, no account needed). Baked into the image rather than downloaded at
# runtime so the container starts offline and deterministically.
#
# It lives in /app/models, NOT /app/storage/models: compose mounts a volume over
# /app/storage, which would shadow anything baked in there. The app would then
# silently fall back to hand-built features - 79.5% against this model's 94.0% -
# and nothing in the logs of a healthy-looking container would say why.
# SPEAKER_MODEL_PATH below points at the real location.
ADD --chown=meetmind:meetmind \
    https://huggingface.co/onnx-community/wespeaker-voxceleb-resnet34-LM/resolve/main/onnx/model.onnx \
    /app/models/wespeaker.onnx
RUN test -s /app/models/wespeaker.onnx || (echo "speaker model download failed" && exit 1)

ENV SPEAKER_MODEL_PATH=/app/models/wespeaker.onnx

USER meetmind

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/app/storage/models

EXPOSE 8000

# Hits the real health endpoint, which genuinely checks the database and the LLM -
# so an unhealthy container is reported unhealthy rather than merely "up".
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
