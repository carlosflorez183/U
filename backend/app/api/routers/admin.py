"""Administración protegida de dispositivos y credenciales de ingesta."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Response, status
from starlette.concurrency import run_in_threadpool

from app.api.admin_schemas import (
    CredentialCreateRequest,
    CredentialCreatedResponse,
    CredentialSummaryResponse,
    DeviceAliasRequest,
    DeviceCreateRequest,
    DeviceResponse,
)
from app.api.dependencies import get_admin_service, require_admin
from app.api.telemetry_schemas import IDENTIFIER_PATTERN
from app.application.admin_service import AdminService

router = APIRouter(
    prefix="/api/v2/admin",
    tags=["Administración IoT"],
    dependencies=[Depends(require_admin)],
)
DevicePath = Annotated[
    str,
    Path(min_length=2, max_length=64, pattern=IDENTIFIER_PATTERN),
]


@router.post(
    "/devices",
    response_model=DeviceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_device(
    payload: DeviceCreateRequest,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> DeviceResponse:
    device = await run_in_threadpool(
        service.register_device,
        group_id=payload.group_id,
        device_id=payload.device_id,
        alias=payload.alias,
    )
    return DeviceResponse.from_domain(device)


@router.get("/devices", response_model=list[DeviceResponse])
async def list_devices(
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> list[DeviceResponse]:
    devices = await run_in_threadpool(service.list_devices)
    return [DeviceResponse.from_domain(device) for device in devices]


@router.post("/devices/{device_id}/activate", response_model=DeviceResponse)
async def activate_device(
    device_id: DevicePath,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> DeviceResponse:
    device = await run_in_threadpool(service.set_device_active, device_id, True)
    return DeviceResponse.from_domain(device)


@router.post("/devices/{device_id}/deactivate", response_model=DeviceResponse)
async def deactivate_device(
    device_id: DevicePath,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> DeviceResponse:
    device = await run_in_threadpool(service.set_device_active, device_id, False)
    return DeviceResponse.from_domain(device)


@router.post("/devices/{device_id}/alias", response_model=DeviceResponse)
async def update_device_alias(
    device_id: DevicePath,
    payload: DeviceAliasRequest,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> DeviceResponse:
    device = await run_in_threadpool(
        service.update_device_alias,
        device_id,
        payload.alias,
    )
    return DeviceResponse.from_domain(device)


@router.post(
    "/credentials",
    response_model=CredentialCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_credential(
    payload: CredentialCreateRequest,
    response: Response,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> CredentialCreatedResponse:
    created = await run_in_threadpool(
        service.create_credential,
        device_id=payload.device_id,
        alias=payload.alias,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return CredentialCreatedResponse.from_created(created)


@router.get("/credentials", response_model=list[CredentialSummaryResponse])
async def list_credentials(
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> list[CredentialSummaryResponse]:
    credentials = await run_in_threadpool(service.list_credentials)
    return [
        CredentialSummaryResponse.from_domain(credential)
        for credential in credentials
    ]


@router.post(
    "/credentials/{credential_id}/revoke",
    response_model=CredentialSummaryResponse,
)
async def revoke_credential(
    credential_id: UUID,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> CredentialSummaryResponse:
    credential = await run_in_threadpool(
        service.revoke_credential,
        str(credential_id),
    )
    return CredentialSummaryResponse.from_domain(credential)
