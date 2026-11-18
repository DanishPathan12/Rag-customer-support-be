from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
