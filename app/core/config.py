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
    pinecone_api_key: SecretStr | None = None
    pinecone_index_name: str | None = None
    pinecone_namespace: str = "customer-support"
    gemini_embedding_model: str = "gemini-embedding-2"
    gemini_embedding_dimensions: int = Field(default=768, gt=0)
    pinecone_metric: str = "cosine"
    ingestion_chunk_size: int = Field(default=1000, gt=0)
    ingestion_chunk_overlap: int = Field(default=200, ge=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
