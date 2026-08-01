from enum import StrEnum
from os import X_OK, access
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, PostgresDsn, RedisDsn, model_validator
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
    redis_url: RedisDsn = RedisDsn("redis://localhost:6379/0")
    rate_limit_enabled: bool = False
    analysis_queue_name: str = "boardtrace.analysis.jobs"
    analysis_lease_seconds: int = Field(default=240, ge=30, le=3600)
    analysis_heartbeat_seconds: int = Field(default=30, ge=5, le=300)
    analysis_task_soft_time_limit_seconds: int = Field(default=170, ge=30, le=179)
    analysis_task_time_limit_seconds: int = Field(default=180, ge=60, le=180)
    analysis_automatic_retry_enabled: bool = False
    analysis_retry_base_delay_seconds: int = Field(default=30, ge=1, le=3600)
    analysis_retry_max_delay_seconds: int = Field(default=900, ge=1, le=86400)
    analysis_retry_max_jitter_seconds: int = Field(default=5, ge=0, le=300)
    stockfish_path: str | None = None
    stockfish_threads: int = Field(default=1, ge=1, le=128)
    stockfish_hash_mb: int = Field(default=64, ge=1, le=65_536)
    stockfish_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    analysis_depth: int = Field(default=12, ge=1, le=99)
    analysis_max_position_time_ms: int = Field(default=500, ge=1, le=300_000)
    analysis_max_game_time_ms: int = Field(default=60_000, ge=1, le=7_200_000)
    analysis_max_moves: int = Field(default=300, ge=1, le=600)
    analysis_max_positions: int = Field(default=301, ge=2, le=601)
    jwt_signing_secret: str | None = Field(default=None, repr=False)
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "boardtrace-api"
    jwt_audience: str = "boardtrace-clients"
    extension_jwt_audience: str = "boardtrace-extension"
    access_token_lifetime_seconds: int = Field(default=900, ge=60, le=3600)
    extension_access_token_lifetime_seconds: int = Field(default=600, ge=60, le=3600)
    extension_pairing_lifetime_seconds: int = Field(default=300, ge=60, le=900)
    refresh_token_lifetime_seconds: int = Field(default=2_592_000, ge=3600, le=7_776_000)
    refresh_token_pepper: str | None = Field(default=None, repr=False)
    password_min_length: int = Field(default=12, ge=8, le=128)
    password_max_length: int = Field(default=256, ge=12, le=1024)

    @model_validator(mode="after")
    def validate_cors(self) -> "Settings":
        if self.environment is Environment.PRODUCTION and "*" in self.cors_allowed_origins:
            raise ValueError("Production CORS origins cannot include wildcard")
        if self.analysis_heartbeat_seconds >= self.analysis_lease_seconds:
            raise ValueError("Analysis heartbeat must be shorter than the lease")
        if self.analysis_task_soft_time_limit_seconds >= self.analysis_task_time_limit_seconds:
            raise ValueError("Analysis soft time limit must be shorter than the hard time limit")
        if self.analysis_task_time_limit_seconds >= self.analysis_lease_seconds:
            raise ValueError("Analysis hard time limit must be shorter than the worker lease")
        if self.analysis_retry_max_delay_seconds < self.analysis_retry_base_delay_seconds:
            raise ValueError("Analysis retry maximum delay must not be below its base delay")
        if self.analysis_max_positions < self.analysis_max_moves + 1:
            raise ValueError("Analysis position budget must include every move plus the start")
        if self.analysis_max_game_time_ms >= self.analysis_lease_seconds * 1000:
            raise ValueError("Analysis game budget must be shorter than the worker lease")
        if self.environment is Environment.PRODUCTION:
            self._validate_production()
        return self

    def _validate_production(self) -> None:
        required = {
            "cors_allowed_origins",
            "database_url",
            "jwt_signing_secret",
            "log_format",
            "redis_url",
            "refresh_token_pepper",
            "stockfish_path",
            "trusted_hosts",
        }
        missing = sorted(required - self.model_fields_set)
        if missing:
            raise ValueError(
                "Production configuration requires explicit values for: " + ", ".join(missing)
            )
        if self.debug or self.database_echo:
            raise ValueError("Production debug and database echo must be disabled")
        if self.log_format is not LogFormat.JSON:
            raise ValueError("Production logging must use JSON format")
        if self.jwt_algorithm != "HS256":
            raise ValueError("Production JWT algorithm must remain HS256")
        if (
            self.jwt_signing_secret is None
            or len(self.jwt_signing_secret) < 32
            or self.refresh_token_pepper is None
            or len(self.refresh_token_pepper) < 32
            or self.jwt_signing_secret == self.refresh_token_pepper
        ):
            raise ValueError("Production authentication secrets must be distinct and strong")
        if self.analysis_queue_name != "boardtrace.analysis.jobs":
            raise ValueError("Production analysis queue name is fixed")
        if not self.rate_limit_enabled:
            raise ValueError("Production shared rate limiting must be enabled")
        if self.analysis_automatic_retry_enabled:
            raise ValueError("Production automatic analysis retry must be disabled")
        if not self.cors_allowed_origins:
            raise ValueError("Production CORS origins must be explicit")
        for origin in self.cors_allowed_origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in ("", "/")
                or parsed.query
                or parsed.fragment
                or parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            ):
                raise ValueError("Production CORS origins must be explicit HTTPS origins")
        if not self.trusted_hosts or any(
            host in {"*", "localhost", "127.0.0.1", "testserver", "::1"}
            or "://" in host
            or "/" in host
            for host in self.trusted_hosts
        ):
            raise ValueError("Production trusted hosts must be explicit deployment hostnames")
        database = urlsplit(str(self.database_url))
        if database.username == "boardtrace" or database.password == "boardtrace":
            raise ValueError("Production database credentials cannot use development defaults")
        stockfish = Path(self.stockfish_path or "")
        if not stockfish.is_file() or not access(stockfish, X_OK):
            raise ValueError("Production Stockfish path must be an executable regular file")
