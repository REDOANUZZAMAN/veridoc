"""Central configuration. Every tunable is an environment variable - no secrets in code."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Versions are surfaced in every report so a finding can always be traced back
# to the exact code that produced it.
PIPELINE_VERSION = "1.4.0"
RULES_VERSION = "2026.09.1"
RISK_WEIGHTS_VERSION = "2026.09.1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore"
    )

    # --- app ---
    app_name: str = "VeriDoc Insurance Document Intelligence"
    app_env: Literal["development", "staging", "production", "test"] = "development"
    api_prefix: str = "/api"
    debug: bool = False
    demo_mode: bool = True

    # --- database ---
    database_url: str = "postgresql+psycopg://veridoc:veridoc@localhost:55432/veridoc"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False

    # --- auth ---
    jwt_secret: str = "change-me-in-production-please-use-a-64-char-random-string"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 45
    refresh_token_ttl_days: int = 7
    password_hash_scheme: Literal["argon2", "bcrypt"] = "argon2"
    signed_url_ttl_seconds: int = 300

    # --- cors / security ---
    allowed_origins: str = "http://localhost:3010,http://127.0.0.1:3010"
    trusted_hosts: str = "*"
    enable_https_redirect: bool = False
    rate_limit_default: str = "300/minute"
    rate_limit_login: str = "10/minute"
    rate_limit_upload: str = "40/minute"

    # --- uploads ---
    max_upload_mb: int = 25
    allowed_mime_types: str = (
        "application/pdf,image/jpeg,image/png,image/tiff"
    )
    allowed_extensions: str = "pdf,jpg,jpeg,png,tif,tiff"
    max_page_count: int = 60
    render_dpi: int = 150

    # --- storage ---
    storage_provider: Literal["local", "s3"] = "local"
    storage_local_root: str = "./var/storage"
    s3_endpoint_url: str | None = None
    s3_region: str = "us-east-1"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_bucket_originals: str = "veridoc-originals"
    s3_bucket_artifacts: str = "veridoc-artifacts"
    s3_force_path_style: bool = True
    s3_server_side_encryption: str | None = None  # e.g. "AES256" / "aws:kms"

    # --- queue ---
    redis_url: str = "redis://localhost:63799/0"
    queue_mode: Literal["redis", "inline"] = "redis"
    queue_name: str = "veridoc-analysis"
    analysis_timeout_seconds: int = 600

    # --- provider selection (overridable per-install from the admin panel) ---
    ocr_provider: Literal["hybrid", "tesseract", "pdf_text", "demo_fixture"] = "hybrid"
    ocr_language: str = "eng"
    aigc_provider: Literal["demo_heuristic", "remote_http"] = "demo_heuristic"
    aigc_remote_url: str | None = None
    aigc_remote_api_key: str | None = None
    verification_provider: Literal["demo", "remote_http"] = "demo"
    verification_remote_url: str | None = None
    verification_remote_api_key: str | None = None
    malware_scanner: Literal["heuristic", "clamav"] = "heuristic"
    clamav_host: str | None = None
    clamav_port: int = 3310

    # --- privacy ---
    retention_days: int = 365
    pii_log_redaction: bool = True

    # --- seeding ---
    seed_password: str = "Demo!2026"

    @field_validator("allowed_origins", "allowed_mime_types", "allowed_extensions", "trusted_hosts")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @property
    def origin_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def mime_list(self) -> list[str]:
        return [m.strip().lower() for m in self.allowed_mime_types.split(",") if m.strip()]

    @property
    def extension_list(self) -> list[str]:
        return [e.strip().lower().lstrip(".") for e in self.allowed_extensions.split(",") if e.strip()]

    @property
    def trusted_host_list(self) -> list[str]:
        return [h.strip() for h in self.trusted_hosts.split(",") if h.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
