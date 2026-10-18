"""Inyección de dependencias para los adaptadores HTTP."""

from __future__ import annotations

from typing import Annotated

from fastapi import Header, Request
from starlette.concurrency import run_in_threadpool

from app.api.realtime import RecordEventHub
from app.application.admin_service import AdminService, IngestAuthenticator
from app.application.errors import AuthenticationError
from app.application.menu_service import MenuService
from app.application.services import RecordService
from app.application.telemetry_service import TelemetryService
from app.domain.auth import IngestPrincipal
from app.infrastructure.security import AdminAuthenticator


def get_record_service(request: Request) -> RecordService:
    """Recupera el caso de uso configurado durante el ciclo de vida de la API."""
    return request.app.state.record_service


def get_record_event_hub(request: Request) -> RecordEventHub:
    """Recupera el canal de notificaciones de la instancia de API actual."""
    return request.app.state.record_event_hub


def get_telemetry_service(request: Request) -> TelemetryService:
    """Recupera los casos de uso de telemetría configurados en la API."""
    return request.app.state.telemetry_service


def get_menu_service(request: Request) -> MenuService:
    """Recupera los casos de uso del menú del teclado matricial."""
    return request.app.state.menu_service


def get_admin_service(request: Request) -> AdminService:
    return request.app.state.admin_service


async def require_admin(
    request: Request,
    api_key: Annotated[str | None, Header(alias="X-Admin-API-Key")] = None,
    secret_key: Annotated[str | None, Header(alias="X-Admin-Secret-Key")] = None,
) -> None:
    if not api_key or not secret_key:
        raise AuthenticationError("Se requieren credenciales administrativas.")
    authenticator: AdminAuthenticator = request.app.state.admin_authenticator
    if not authenticator.verify(api_key, secret_key):
        raise AuthenticationError("Credenciales administrativas inválidas.")


async def require_ingest_principal(
    request: Request,
    api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    secret_key: Annotated[str | None, Header(alias="X-Secret-Key")] = None,
) -> IngestPrincipal:
    if not api_key or not secret_key:
        raise AuthenticationError("Se requieren X-API-Key y X-Secret-Key.")
    authenticator: IngestAuthenticator = request.app.state.ingest_authenticator
    return await run_in_threadpool(
        authenticator.authenticate,
        api_key,
        secret_key,
    )
