from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_repository_env(config_path: Path, cwd: Path) -> Path:
    """Find the checkout-level env file without assuming an install depth."""
    for parent in config_path.parents:
        if (parent / "Makefile").is_file() and (parent / "apps").is_dir():
            return parent / ".env"
    return cwd / ".env"


REPOSITORY_ENV = _find_repository_env(Path(__file__).resolve(), Path.cwd())
DEFAULT_DATA_DIR = Path.home() / ".local" / "share" / "citetrail"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPOSITORY_ENV, ".env"),
        env_prefix="CITETRAIL_",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "CiteTrail"
    environment: str = "development"
    data_dir: Path = DEFAULT_DATA_DIR
    database_url: str | None = None
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    allow_http_urls: bool = False
    max_redirects: int = Field(default=5, ge=0, le=20)
    request_timeout_seconds: float = Field(default=20.0, gt=0, le=300)
    max_download_bytes: int = Field(default=20 * 1024 * 1024, ge=1, le=200 * 1024 * 1024)
    max_upload_bytes: int = Field(default=50 * 1024 * 1024, ge=1, le=500 * 1024 * 1024)
    max_extracted_chars: int = Field(default=2_000_000, ge=1, le=20_000_000)
    max_pdf_pages: int = Field(default=1000, ge=1, le=10_000)
    chunk_size: int = Field(default=1200, ge=100, le=20_000)
    chunk_overlap: int = Field(default=150, ge=0, le=10_000)
    ingestion_poll_seconds: float = Field(default=0.5, ge=0.05, le=10)
    semantic_search_enabled: bool = True
    embedding_model: str = "deterministic-feature-hash-v1"
    model_provider: str = "ollama"
    model_base_url: str = "http://127.0.0.1:11434"
    model_name: str = "qwen2.5:7b"
    model_api_key: str | None = None
    model_temperature: float = 0.1
    model_max_tokens: int = 1200
    model_timeout_seconds: float = Field(default=60.0, gt=0, le=600)
    model_retry_count: int = Field(default=1, ge=0, le=10)

    @field_validator("data_dir", mode="before")
    @classmethod
    def expand_data_dir(cls, value: object) -> Path:
        return Path(str(value)).expanduser().resolve()

    @field_validator("model_provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        if value not in {"ollama", "openai_compatible"}:
            raise ValueError("model_provider must be ollama or openai_compatible")
        return value

    @field_validator("model_base_url")
    @classmethod
    def validate_model_base_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("model_base_url must be an HTTP(S) URL with a hostname")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("model_base_url must not contain embedded credentials")
        return value.rstrip("/")

    @model_validator(mode="after")
    def validate_chunk_shape(self) -> Settings:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return self

    @property
    def resolved_database_url(self) -> str:
        return self.database_url or f"sqlite:///{self.data_dir / 'citetrail.db'}"

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def vector_dir(self) -> Path:
        return self.data_dir / "vectors"

    def ensure_directories(self) -> None:
        for path in (self.data_dir, self.upload_dir, self.vector_dir):
            path.mkdir(parents=True, exist_ok=True, mode=0o700)


@lru_cache
def get_settings() -> Settings:
    return Settings()
