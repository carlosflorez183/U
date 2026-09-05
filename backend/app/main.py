"""Punto de entrada de la API FastAPI."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from psycopg import Error as PostgresError

from app.api.error_handling import ErrorHandlingMiddleware, install_exception_handlers
from app.api.realtime import RecordEventHub
from app.api.routers.admin import router as admin_router
from app.api.routers.records import router as records_router
from app.api.routers.telemetry import router as telemetry_router
from app.application.admin_service import AdminService, IngestAuthenticator
from app.application.services import RecordService
from app.application.telemetry_service import TelemetryService
from app.infrastructure.config import Settings
from app.infrastructure.database import PostgresDatabase
from app.infrastructure.postgres_admin_repository import PostgresAdminRepository
from app.infrastructure.postgres_record_repository import PostgresRecordRepository
from app.infrastructure.postgres_telemetry_repository import PostgresTelemetryRepository
from app.infrastructure.record_export_renderer import FileRecordExportRenderer
from app.infrastructure.security import AdminAuthenticator, CredentialHasher
from app.infrastructure.telemetry_export_renderer import FileTelemetryExportRenderer

settings = Settings.from_environment()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa adaptadores y siempre libera WebSockets y PostgreSQL."""
    database = PostgresDatabase(
        settings.database_url,
        min_size=settings.database_pool_min_size,
        max_size=settings.database_pool_max_size,
    )
    event_hub: RecordEventHub | None = None
    try:
        database.open()
        database.verify_schema()

        app.state.database = database
        credential_hasher = CredentialHasher(settings.credential_pepper)
        admin_repository = PostgresAdminRepository(database, credential_hasher)
        app.state.admin_authenticator = AdminAuthenticator(
            settings.admin_api_key,
            settings.admin_secret_key,
        )
        app.state.admin_service = AdminService(
            admin_repository,
            credential_hasher,
        )
        app.state.ingest_authenticator = IngestAuthenticator(admin_repository)
        app.state.record_service = RecordService(
            PostgresRecordRepository(database), FileRecordExportRenderer()
        )
        app.state.telemetry_service = TelemetryService(
            PostgresTelemetryRepository(database), FileTelemetryExportRenderer()
        )
        event_hub = RecordEventHub()
        app.state.record_event_hub = event_hub
        yield
    finally:
        if event_hub is not None:
            try:
                await event_hub.close_all()
            finally:
                database.close()
        else:
            database.close()


app = FastAPI(
    title="API de monitoreo agrícola IoT",
    version="3.1.0",
    description=(
        "Ingesta y consulta de humedad capacitiva del suelo y detección de lluvia "
        "sobre PostgreSQL/TimescaleDB. La API v1 se conserva por compatibilidad."
    ),
    lifespan=lifespan,
)
install_exception_handlers(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=[
        "Content-Type",
        "X-Request-ID",
        "X-API-Key",
        "X-Secret-Key",
        "X-Admin-API-Key",
        "X-Admin-Secret-Key",
    ],
    expose_headers=["Content-Disposition", "X-Request-ID", "X-Process-Time-Ms"],
)
# Se agrega después de CORS para que sea la barrera ASGI más externa.
app.add_middleware(
    ErrorHandlingMiddleware,
    max_telemetry_body_bytes=settings.max_telemetry_body_bytes,
    max_legacy_body_bytes=settings.max_legacy_body_bytes,
)
app.include_router(telemetry_router)
app.include_router(admin_router)
app.include_router(records_router, deprecated=True)


@app.get("/health", tags=["Sistema"])
@app.get("/health/live", tags=["Sistema"])
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["Sistema"])
def readiness(request: Request) -> dict[str, str]:
    """Comprueba PostgreSQL y el pool usado por la API."""
    try:
        request.app.state.database.ping()
    except PostgresError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PostgreSQL no está disponible.",
        ) from exc
    return {
        "status": "ready",
        "database": "connected",
        "engine": "postgresql",
        "timescaledb": "active",
    }
