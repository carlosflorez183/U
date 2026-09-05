"""Entidades inmutables para administración y autenticación de dispositivos."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class IngestPrincipal:
    """Identidad autenticada, sin transportar material secreto."""

    credential_id: str
    credential_alias: str
    device_uuid: str
    device_id: str
    device_alias: str
    group_id: str


@dataclass(frozen=True, slots=True)
class ManagedDevice:
    id: str
    group_id: str
    device_id: str
    alias: str
    active: bool
    created_at: datetime
    last_seen_at: datetime | None


@dataclass(frozen=True, slots=True)
class DeviceCredential:
    id: str
    device_id: str
    device_alias: str
    alias: str
    api_key_prefix: str
    active: bool
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None
