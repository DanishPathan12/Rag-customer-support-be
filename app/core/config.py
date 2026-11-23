from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    database_url: str
    jwt_secret: SecretStr = Field(min_length=32)
    otp_pepper: SecretStr = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "ecommerce-customer-support"
    access_token_minutes: int = Field(default=60, gt=0)
    otp_ttl_minutes: int = Field(default=5, gt=0)
    otp_resend_cooldown_seconds: int = Field(default=60, gt=0)
    otp_max_attempts: int = Field(default=5, gt=0)
    mail_host: str | None = None
    mail_port: int = Field(default=587, gt=0)
    mail_username: str | None = None
    mail_password: SecretStr | None = None
    mail_from: str | None = None
    mail_starttls: bool = True
    ingestion_dir: Path = PROJECT_ROOT / "ingestion"
    ingestion_max_upload_bytes: int = Field(default=20 * 1024 * 1024, gt=0)
    google_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_API_KEY", "GEMINI_API_KEY"),
    )
    gemini_embedding_model: str = "gemini-embedding-2"
    gemini_embedding_dimensions: int = Field(default=768, gt=0)
    gemini_embedding_batch_size: int = Field(default=100, gt=0, le=100)
    gemini_embedding_max_retries: int = Field(default=3, ge=0, le=10)
    gemini_embedding_min_request_interval_seconds: float = Field(default=0.7, ge=0)
    gemini_response_model: str = "gemini-3.8-flash"
    gemini_response_fallback_model: str = "gemini-3.5-flash-lite"
    gemini_response_max_output_tokens: int = Field(default=512, gt=0, le=4096)
    gemini_response_temperature: float = Field(default=0.1, ge=0, le=1)
    gemini_response_max_retries: int = Field(default=2, ge=0, le=5)
    gemini_response_retry_delay_seconds: float = Field(default=1, gt=0, le=30)
    chroma_host: str = "localhost"
    chroma_port: int = Field(default=8001, gt=0, le=65535)
    chroma_ssl: bool = False
    chroma_tenant: str = "default_tenant"
    chroma_database: str = "default_database"
    chroma_collection_name: str = "customer-support-knowledge"
    rag_top_k: int = Field(default=4, gt=0, le=10)
    ingestion_chunk_size: int = Field(default=1000, gt=0)
    ingestion_chunk_overlap: int = Field(default=200, ge=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
