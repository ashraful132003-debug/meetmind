"""Application configuration, loaded from environment / .env.

Nothing here is ever exposed to the frontend. Values that would be unsafe to
default (secrets) fail loudly in production rather than falling back.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]

_PLACEHOLDERS = {
    "change-me-to-a-long-random-string",
    "change-me-to-a-fernet-key",
    "change-me-to-another-long-random-string",
    "change-me-local-db-password",
    "",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_name: str = "MeetMind"
    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    frontend_origin: str = "http://localhost:5173"

    jwt_secret: str
    encryption_key: str
    media_signing_secret: str

    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 14

    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5433
    postgres_db: str = "meetmind"
    postgres_user: str = "meetmind"
    postgres_password: str

    llm_provider: str = "ollama"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_chat_model: str = "llama3.2:3b"
    ollama_embed_model: str = "all-minilm"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    whisper_model: str = "small"
    whisper_device: str = "auto"
    whisper_compute_type: str = "int8"

    # Speaker-recognition model for diarization. Relative paths resolve against
    # the repo root. Kept configurable because in Docker it must live OUTSIDE
    # /app/storage: that path is a mounted volume, which would shadow anything
    # baked into the image and silently drop diarization from 94% to 79.5%.
    speaker_model_path: str = "./storage/models/wespeaker.onnx"

    email_transport: str = "local"
    email_from: str = "MeetMind <no-reply@meetmind.local>"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True

    media_dir: str = "./storage/media"
    max_upload_mb: int = 200

    rate_limit_login_per_minute: int = 5
    rate_limit_upload_per_hour: int = 30

    @field_validator("jwt_secret", "encryption_key", "media_signing_secret")
    @classmethod
    def _reject_placeholder_secrets(cls, v: str, info) -> str:
        if v in _PLACEHOLDERS:
            raise ValueError(
                f"{info.field_name} is unset or still the placeholder value. "
                f"Run `python scripts/bootstrap_env.py` to generate real secrets."
            )
        return v

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def media_path(self) -> Path:
        p = (BASE_DIR / self.media_dir).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def speaker_model_file(self) -> Path:
        p = Path(self.speaker_model_path)
        return p if p.is_absolute() else (BASE_DIR / p).resolve()

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.frontend_origin.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
