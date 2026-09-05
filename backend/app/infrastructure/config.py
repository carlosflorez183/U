"""Configuración leída desde variables de entorno."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    database_pool_min_size: int
    database_pool_max_size: int
    cors_origins: list[str]
    max_telemetry_body_bytes: int
    max_legacy_body_bytes: int
    credential_pepper: str
    admin_api_key: str
    admin_secret_key: str

    def __post_init__(self) -> None:
        if not self.database_url.strip():
            raise ValueError("DATABASE_URL no puede estar vacía.")
        if self.database_pool_min_size < 1:
            raise ValueError("DATABASE_POOL_MIN_SIZE debe ser al menos 1.")
        if self.database_pool_max_size < self.database_pool_min_size:
            raise ValueError(
                "DATABASE_POOL_MAX_SIZE no puede ser menor que DATABASE_POOL_MIN_SIZE."
            )
        if self.max_telemetry_body_bytes < 1024:
            raise ValueError("MAX_TELEMETRY_BODY_BYTES debe ser al menos 1024.")
        if self.max_legacy_body_bytes < 1024:
            raise ValueError("MAX_LEGACY_BODY_BYTES debe ser al menos 1024.")
        for variable, value, minimum in (
            ("CREDENTIAL_PEPPER", self.credential_pepper, 32),
            ("ADMIN_API_KEY", self.admin_api_key, 16),
            ("ADMIN_SECRET_KEY", self.admin_secret_key, 24),
        ):
            if len(value) < minimum:
                raise ValueError(f"{variable} debe tener al menos {minimum} caracteres.")

    @classmethod
    def from_environment(cls) -> "Settings":
        origins = os.getenv("CORS_ORIGINS", "http://localhost:8501")
        return cls(
            database_url=os.getenv(
                "DATABASE_URL",
                "postgresql://agro_iot:change-me@localhost:5432/agro_iot",
            ),
            database_pool_min_size=int(os.getenv("DATABASE_POOL_MIN_SIZE", "1")),
            database_pool_max_size=int(os.getenv("DATABASE_POOL_MAX_SIZE", "10")),
            cors_origins=[origin.strip() for origin in origins.split(",") if origin.strip()],
            max_telemetry_body_bytes=int(
                os.getenv("MAX_TELEMETRY_BODY_BYTES", str(64 * 1024))
            ),
            max_legacy_body_bytes=int(
                os.getenv("MAX_LEGACY_BODY_BYTES", str(1024 * 1024))
            ),
            credential_pepper=os.getenv(
                "CREDENTIAL_PEPPER",
                "development-only-change-this-credential-pepper",
            ),
            admin_api_key=os.getenv(
                "ADMIN_API_KEY",
                "admin-api-key-change-me",
            ),
            admin_secret_key=os.getenv(
                "ADMIN_SECRET_KEY",
                "admin-secret-key-change-me-now",
            ),
        )
