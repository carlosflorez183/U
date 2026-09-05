"""Casos de uso administrativos y autenticación de ingesta."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.errors import AuthenticationError
from app.domain.auth import DeviceCredential, IngestPrincipal, ManagedDevice
from app.infrastructure.postgres_admin_repository import PostgresAdminRepository
from app.infrastructure.security import CredentialHasher


@dataclass(frozen=True, slots=True)
class CreatedCredential:
    credential: DeviceCredential
    api_key: str
    secret_key: str


class IngestAuthenticator:
    def __init__(self, repository: PostgresAdminRepository) -> None:
        self._repository = repository

    def authenticate(self, api_key: str, secret_key: str) -> IngestPrincipal:
        principal = self._repository.authenticate(api_key, secret_key)
        if principal is None:
            raise AuthenticationError("Credenciales de ingesta inválidas.")
        return principal


class AdminService:
    def __init__(
        self,
        repository: PostgresAdminRepository,
        hasher: CredentialHasher,
    ) -> None:
        self._repository = repository
        self._hasher = hasher

    def register_device(
        self, *, group_id: str, device_id: str, alias: str
    ) -> ManagedDevice:
        return self._repository.register_device(
            group_id=group_id,
            device_id=device_id,
            alias=alias,
        )

    def list_devices(self) -> list[ManagedDevice]:
        return self._repository.list_devices()

    def set_device_active(self, device_id: str, active: bool) -> ManagedDevice:
        return self._repository.set_device_active(device_id, active)

    def update_device_alias(self, device_id: str, alias: str) -> ManagedDevice:
        return self._repository.update_device_alias(device_id, alias)

    def create_credential(self, *, device_id: str, alias: str) -> CreatedCredential:
        material = self._hasher.generate()
        credential = self._repository.create_credential(
            device_id=device_id,
            alias=alias,
            material=material,
        )
        return CreatedCredential(
            credential=credential,
            api_key=material.api_key,
            secret_key=material.secret_key,
        )

    def list_credentials(self) -> list[DeviceCredential]:
        return self._repository.list_credentials()

    def revoke_credential(self, credential_id: str) -> DeviceCredential:
        return self._repository.revoke_credential(credential_id)
