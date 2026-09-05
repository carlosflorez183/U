"""DTOs estrictos de administración de dispositivos y credenciales."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.telemetry_schemas import IDENTIFIER_PATTERN
from app.application.admin_service import CreatedCredential
from app.domain.auth import DeviceCredential, ManagedDevice

_STRICT = ConfigDict(extra="forbid", strict=True)


class DeviceCreateRequest(BaseModel):
    model_config = _STRICT

    group_id: str = Field(
        strict=True, min_length=2, max_length=64, pattern=IDENTIFIER_PATTERN
    )
    device_id: str = Field(
        strict=True, min_length=2, max_length=64, pattern=IDENTIFIER_PATTERN
    )
    alias: str = Field(strict=True, min_length=2, max_length=120)

    @field_validator("alias")
    @classmethod
    def alias_without_outer_spaces(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("alias no debe tener espacios externos.")
        return value


class DeviceAliasRequest(BaseModel):
    model_config = _STRICT

    alias: str = Field(strict=True, min_length=2, max_length=120)

    @field_validator("alias")
    @classmethod
    def alias_without_outer_spaces(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("alias no debe tener espacios externos.")
        return value


class DeviceResponse(BaseModel):
    id: str
    group_id: str
    device_id: str
    alias: str
    active: bool
    created_at: datetime
    last_seen_at: datetime | None

    @classmethod
    def from_domain(cls, device: ManagedDevice) -> "DeviceResponse":
        return cls(**{field: getattr(device, field) for field in cls.model_fields})


class CredentialCreateRequest(BaseModel):
    model_config = _STRICT

    device_id: str = Field(
        strict=True, min_length=2, max_length=64, pattern=IDENTIFIER_PATTERN
    )
    alias: str = Field(strict=True, min_length=2, max_length=120)

    @field_validator("alias")
    @classmethod
    def alias_without_outer_spaces(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("alias no debe tener espacios externos.")
        return value


class CredentialSummaryResponse(BaseModel):
    id: str
    device_id: str
    device_alias: str
    alias: str
    api_key_prefix: str
    active: bool
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None

    @classmethod
    def from_domain(
        cls, credential: DeviceCredential
    ) -> "CredentialSummaryResponse":
        return cls(**{field: getattr(credential, field) for field in cls.model_fields})


class CredentialCreatedResponse(CredentialSummaryResponse):
    api_key: str
    secret_key: str
    warning: str = "Guarde el secret_key ahora: no se puede recuperar después."

    @classmethod
    def from_created(cls, created: CreatedCredential) -> "CredentialCreatedResponse":
        values = {
            field: getattr(created.credential, field)
            for field in CredentialSummaryResponse.model_fields
        }
        return cls(
            **values,
            api_key=created.api_key,
            secret_key=created.secret_key,
        )
