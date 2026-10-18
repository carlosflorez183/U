"""Persistencia administrativa de dispositivos y credenciales de ingesta."""

from __future__ import annotations

from datetime import timezone
from typing import Any

from psycopg.types.json import Jsonb

from app.application.errors import ResourceConflictError, ResourceNotFoundError
from app.domain.auth import DeviceCredential, IngestPrincipal, ManagedDevice
from app.infrastructure.database import PostgresDatabase
from app.infrastructure.security import CredentialHasher, GeneratedCredential


class PostgresAdminRepository:
    def __init__(self, database: PostgresDatabase, hasher: CredentialHasher) -> None:
        self._database = database
        self._hasher = hasher

    def register_device(
        self,
        *,
        group_id: str,
        device_id: str,
        alias: str,
    ) -> ManagedDevice:
        with self._database.pool.connection() as connection:
            with connection.transaction():
                group_uuid = connection.execute(
                    """
                    INSERT INTO iot_groups(code, name)
                    VALUES (%s, %s)
                    ON CONFLICT (code) DO UPDATE SET name = iot_groups.name
                    RETURNING id
                    """,
                    (group_id, group_id),
                ).fetchone()["id"]
                row = connection.execute(
                    """
                    INSERT INTO devices(group_id, external_id, name)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (external_id) DO NOTHING
                    RETURNING id, external_id, name, active, created_at, last_seen_at
                    """,
                    (group_uuid, device_id, alias),
                ).fetchone()
                if row is None:
                    raise ResourceConflictError("El dispositivo ya está registrado.")
                # DHT22 ambiental: temperatura + humedad. Fallback a tipos
                # antiguos si la migración 004 aún no corrió.
                try:
                    self._create_default_sensor(
                        connection,
                        device_uuid=row["id"],
                        sensor_type="temperature",
                        external_id="dht22-temp",
                        pin="GPIO4",
                    )
                    self._create_default_sensor(
                        connection,
                        device_uuid=row["id"],
                        sensor_type="humidity",
                        external_id="dht22-hum",
                        pin="GPIO4",
                    )
                except RuntimeError:
                    self._create_default_sensor(
                        connection,
                        device_uuid=row["id"],
                        sensor_type="soil_moisture",
                        external_id="soil-capacitive",
                        pin="GPIO34",
                    )
                    self._create_default_sensor(
                        connection,
                        device_uuid=row["id"],
                        sensor_type="rain_wetness",
                        external_id="rain-board",
                        pin="GPIO35/GPIO27",
                    )
        return ManagedDevice(
            id=str(row["id"]),
            group_id=group_id,
            device_id=str(row["external_id"]),
            alias=str(row["name"]),
            active=bool(row["active"]),
            created_at=_utc(row["created_at"]),
            last_seen_at=_utc_optional(row["last_seen_at"]),
        )

    def list_devices(self) -> list[ManagedDevice]:
        with self._database.pool.connection() as connection:
            rows = connection.execute(
                """
                SELECT device.id, grp.code AS group_id, device.external_id,
                       device.name, device.active, device.created_at, device.last_seen_at
                FROM devices device
                JOIN iot_groups grp ON grp.id = device.group_id
                ORDER BY device.created_at DESC, device.external_id
                """
            ).fetchall()
        return [_device_from_row(row) for row in rows]

    def set_device_active(self, device_id: str, active: bool) -> ManagedDevice:
        with self._database.pool.connection() as connection:
            row = connection.execute(
                """
                UPDATE devices SET active = %s
                WHERE external_id = %s
                RETURNING id, external_id, name, active, created_at, last_seen_at,
                          (SELECT code FROM iot_groups WHERE id = devices.group_id) AS group_id
                """,
                (active, device_id),
            ).fetchone()
        if row is None:
            raise ResourceNotFoundError("El dispositivo no existe.")
        return _device_from_row(row)

    def update_device_alias(self, device_id: str, alias: str) -> ManagedDevice:
        with self._database.pool.connection() as connection:
            row = connection.execute(
                """
                UPDATE devices SET name = %s
                WHERE external_id = %s
                RETURNING id, external_id, name, active, created_at, last_seen_at,
                          (SELECT code FROM iot_groups WHERE id = devices.group_id) AS group_id
                """,
                (alias, device_id),
            ).fetchone()
        if row is None:
            raise ResourceNotFoundError("El dispositivo no existe.")
        return _device_from_row(row)

    def create_credential(
        self,
        *,
        device_id: str,
        alias: str,
        material: GeneratedCredential,
    ) -> DeviceCredential:
        with self._database.pool.connection() as connection:
            row = connection.execute(
                """
                INSERT INTO device_credentials(
                    device_id, alias, api_key_digest, api_key_prefix,
                    secret_salt, secret_hash
                )
                SELECT device.id, %s, %s, %s, %s, %s
                FROM devices device
                WHERE device.external_id = %s
                RETURNING id, device_id, alias, api_key_prefix, active,
                          created_at, last_used_at, revoked_at
                """,
                (
                    alias,
                    material.api_key_digest,
                    material.api_key_prefix,
                    material.secret_salt,
                    material.secret_hash,
                    device_id,
                ),
            ).fetchone()
            if row is None:
                raise ResourceNotFoundError("El dispositivo no existe.")
            device = connection.execute(
                "SELECT external_id, name FROM devices WHERE id = %s",
                (row["device_id"],),
            ).fetchone()
        return _credential_from_rows(row, device)

    def list_credentials(self) -> list[DeviceCredential]:
        with self._database.pool.connection() as connection:
            rows = connection.execute(
                """
                SELECT credential.id, credential.alias, credential.api_key_prefix,
                       credential.active, credential.created_at,
                       credential.last_used_at, credential.revoked_at,
                       device.external_id AS device_id, device.name AS device_alias
                FROM device_credentials credential
                JOIN devices device ON device.id = credential.device_id
                ORDER BY credential.created_at DESC
                """
            ).fetchall()
        return [
            DeviceCredential(
                id=str(row["id"]),
                device_id=str(row["device_id"]),
                device_alias=str(row["device_alias"]),
                alias=str(row["alias"]),
                api_key_prefix=str(row["api_key_prefix"]),
                active=bool(row["active"]),
                created_at=_utc(row["created_at"]),
                last_used_at=_utc_optional(row["last_used_at"]),
                revoked_at=_utc_optional(row["revoked_at"]),
            )
            for row in rows
        ]

    def revoke_credential(self, credential_id: str) -> DeviceCredential:
        with self._database.pool.connection() as connection:
            row = connection.execute(
                """
                UPDATE device_credentials
                SET active = FALSE, revoked_at = COALESCE(revoked_at, now())
                WHERE id = %s
                RETURNING id, device_id, alias, api_key_prefix, active,
                          created_at, last_used_at, revoked_at
                """,
                (credential_id,),
            ).fetchone()
            if row is None:
                raise ResourceNotFoundError("La credencial no existe.")
            device = connection.execute(
                "SELECT external_id, name FROM devices WHERE id = %s",
                (row["device_id"],),
            ).fetchone()
        return _credential_from_rows(row, device)

    def authenticate(self, api_key: str, secret_key: str) -> IngestPrincipal | None:
        digest = self._hasher.digest_api_key(api_key)
        with self._database.pool.connection() as connection:
            row = connection.execute(
                """
                SELECT credential.id AS credential_id,
                       credential.alias AS credential_alias,
                       credential.secret_salt, credential.secret_hash,
                       device.id AS device_uuid, device.external_id AS device_id,
                       device.name AS device_alias, grp.code AS group_id
                FROM device_credentials credential
                JOIN devices device ON device.id = credential.device_id
                JOIN iot_groups grp ON grp.id = device.group_id
                WHERE credential.api_key_digest = %s
                  AND credential.active
                  AND credential.revoked_at IS NULL
                  AND device.active
                """,
                (digest,),
            ).fetchone()
            if row is None:
                self._hasher.consume_dummy_verification(secret_key)
                return None
            if not self._hasher.verify_secret(
                secret_key,
                bytes(row["secret_salt"]),
                bytes(row["secret_hash"]),
            ):
                return None
            connection.execute(
                "UPDATE device_credentials SET last_used_at = now() WHERE id = %s",
                (row["credential_id"],),
            )
        return IngestPrincipal(
            credential_id=str(row["credential_id"]),
            credential_alias=str(row["credential_alias"]),
            device_uuid=str(row["device_uuid"]),
            device_id=str(row["device_id"]),
            device_alias=str(row["device_alias"]),
            group_id=str(row["group_id"]),
        )

    @staticmethod
    def _create_default_sensor(
        connection,
        *,
        device_uuid: Any,
        sensor_type: str,
        external_id: str,
        pin: str,
    ) -> None:
        sensor = connection.execute(
            """
            INSERT INTO sensors(device_id, sensor_type_id, external_id, pin)
            SELECT %s, type.id, %s, %s
            FROM sensor_types type
            WHERE type.code = %s
            RETURNING id
            """,
            (device_uuid, external_id, pin, sensor_type),
        ).fetchone()
        if sensor is None:
            raise RuntimeError(f"No existe el tipo de sensor {sensor_type}.")
        connection.execute(
            """
            INSERT INTO calibrations(sensor_id, version, metadata)
            VALUES (%s, 1, %s)
            """,
            (
                sensor["id"],
                Jsonb(
                    {
                        "status": "pending_hardware_calibration",
                        "source": "percentage_reported_by_firmware",
                    }
                ),
            ),
        )


def _device_from_row(row: dict[str, Any]) -> ManagedDevice:
    return ManagedDevice(
        id=str(row["id"]),
        group_id=str(row["group_id"]),
        device_id=str(row["external_id"]),
        alias=str(row["name"]),
        active=bool(row["active"]),
        created_at=_utc(row["created_at"]),
        last_seen_at=_utc_optional(row["last_seen_at"]),
    )


def _credential_from_rows(
    row: dict[str, Any], device: dict[str, Any]
) -> DeviceCredential:
    return DeviceCredential(
        id=str(row["id"]),
        device_id=str(device["external_id"]),
        device_alias=str(device["name"]),
        alias=str(row["alias"]),
        api_key_prefix=str(row["api_key_prefix"]),
        active=bool(row["active"]),
        created_at=_utc(row["created_at"]),
        last_used_at=_utc_optional(row["last_used_at"]),
        revoked_at=_utc_optional(row["revoked_at"]),
    )


def _utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _utc_optional(value):
    return None if value is None else _utc(value)
