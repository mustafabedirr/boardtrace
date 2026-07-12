from enum import StrEnum

from pydantic import Field, model_validator
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

    @model_validator(mode="after")
    def validate_cors(self) -> "Settings":
        if self.environment is Environment.PRODUCTION and "*" in self.cors_allowed_origins:
            raise ValueError("Production CORS origins cannot include wildcard")
        return self
