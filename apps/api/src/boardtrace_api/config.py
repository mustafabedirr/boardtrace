from enum import StrEnum

from pydantic import Field, PostgresDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class LogFormat(StrEnum):
    CONSOLE = "console"
    JSON = "json"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="BOARDTRACE_", extra="ignore")
    app_name: str = "BoardTrace API"
    app_version: str = "0.1.0"
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"
    log_format: LogFormat = LogFormat.CONSOLE
    cors_allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    trusted_hosts: list[str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "testserver"]
    )
    request_id_header: str = "X-Request-ID"
    database_url: PostgresDsn = PostgresDsn(
        "postgresql+asyncpg://boardtrace:boardtrace@localhost:5432/boardtrace"
    )
    database_echo: bool = False
    database_pool_size: int = Field(default=5, ge=1, le=100)
    database_max_overflow: int = Field(default=10, ge=0, le=100)
    database_pool_timeout: int = Field(default=30, ge=1, le=300)
    database_pool_recycle: int = Field(default=1800, ge=0, le=86400)
    jwt_signing_secret: str | None = Field(default=None, repr=False)
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "boardtrace-api"
    jwt_audience: str = "boardtrace-clients"
    access_token_lifetime_seconds: int = Field(default=900, ge=60, le=3600)
    refresh_token_lifetime_seconds: int = Field(default=2_592_000, ge=3600, le=7_776_000)
    refresh_token_pepper: str | None = Field(default=None, repr=False)
    password_min_length: int = Field(default=12, ge=8, le=128)
    password_max_length: int = Field(default=256, ge=12, le=1024)

    @model_validator(mode="after")
    def validate_cors(self) -> "Settings":
        if self.environment is Environment.PRODUCTION and "*" in self.cors_allowed_origins:
            raise ValueError("Production CORS origins cannot include wildcard")
        return self
