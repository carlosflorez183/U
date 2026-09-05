"""Adaptador PostgreSQL/TimescaleDB para telemetría IoT autenticada."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from app.application.errors import (
    AuthenticationError,
    AuthorizationError,
    ResourceConflictError,
)
from app.domain.telemetry import RainReading, SoilMoistureReading, TelemetrySample
from app.infrastructure.database import PostgresDatabase

_FILTER_COLUMNS = {
    "soil_percent": "soil_moisture_percent",
    "rain_percent": "rain_wetness_percent",
    "soil_adc": "soil_raw_adc",
    "rain_adc": "rain_raw_adc",
}


class PostgresTelemetryRepository:
    """Revalida identidad y persiste una muestra sin auto-crear dispositivos."""

    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def save(self, sample: TelemetrySample) -> tuple[TelemetrySample, bool]:
        if sample.ingest_credential_id is None:
            raise AuthenticationError("La muestra no tiene una credencial autenticada.")
        fingerprint = _payload_fingerprint(sample)
        with self._database.pool.connection() as connection:
            with connection.transaction():
                identity = connection.execute(
                    """
                    SELECT credential.id AS credential_id,
                           credential.alias AS credential_alias,
                           device.id AS device_uuid,
                           device.external_id AS device_id,
                           device.name AS device_alias,
                           grp.code AS group_id
                    FROM device_credentials credential
                    JOIN devices device ON device.id = credential.device_id
                    JOIN iot_groups grp ON grp.id = device.group_id
                    WHERE credential.id = %s
                      AND credential.active
                      AND credential.revoked_at IS NULL
                      AND device.active
                    FOR SHARE OF credential, device
                    """,
                    (sample.ingest_credential_id,),
                ).fetchone()
                if identity is None:
                    raise AuthenticationError(
                        "La credencial fue revocada o el dispositivo está inactivo."
                    )
                if (
                    str(identity["device_id"]) != sample.device_id
                    or str(identity["group_id"]) != sample.group_id
                ):
                    raise AuthorizationError(
                        "La credencial no corresponde al grupo o dispositivo indicado."
                    )

                stored_sample = replace(
                    sample,
                    device_alias=str(identity["device_alias"]),
                    inserted_by_alias=str(identity["credential_alias"]),
                    ingest_credential_id=str(identity["credential_id"]),
                )
                connection.execute(
                    "UPDATE devices SET last_seen_at = %s WHERE id = %s",
                    (stored_sample.received_at, identity["device_uuid"]),
                )
                inserted = connection.execute(
                    """
                    INSERT INTO telemetry_samples(
                        id, device_id, sequence, schema_version, measured_at,
                        received_at, sampling_period_seconds, soil_status, rain_status,
                        ingest_credential_id, device_alias_at_ingest,
                        credential_alias_at_ingest, payload_sha256
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s
                    )
                    ON CONFLICT (device_id, sequence) DO NOTHING
                    RETURNING id
                    """,
                    (
                        stored_sample.id,
                        identity["device_uuid"],
                        stored_sample.sequence,
                        stored_sample.schema_version,
                        stored_sample.measured_at,
                        stored_sample.received_at,
                        stored_sample.sampling_period_seconds,
                        stored_sample.soil_status,
                        stored_sample.rain_status,
                        identity["credential_id"],
                        identity["device_alias"],
                        identity["credential_alias"],
                        fingerprint,
                    ),
                ).fetchone()
                if inserted is None:
                    existing = self._find_by_device_sequence(
                        connection,
                        stored_sample.device_id,
                        stored_sample.sequence,
                    )
                    if existing is None:
                        raise RuntimeError("No se pudo recuperar la muestra idempotente.")
                    existing_fingerprint = existing.get("payload_sha256")
                    if existing_fingerprint is None:
                        existing_fingerprint = _payload_fingerprint(_from_row(existing))
                    if str(existing_fingerprint) != fingerprint:
                        raise ResourceConflictError(
                            "La secuencia ya existe con un contenido diferente."
                        )
                    return _from_row(existing), False

                soil_sensor, soil_calibration = self._get_sensor(
                    connection,
                    device_uuid=identity["device_uuid"],
                    sensor_type="soil_moisture",
                )
                rain_sensor, rain_calibration = self._get_sensor(
                    connection,
                    device_uuid=identity["device_uuid"],
                    sensor_type="rain_wetness",
                )
                connection.cursor().executemany(
                    """
                    INSERT INTO sensor_measurements(
                        sample_id, sensor_id, calibration_id, measured_at,
                        raw_adc, numeric_value, boolean_value
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        (
                            stored_sample.id,
                            soil_sensor,
                            soil_calibration,
                            stored_sample.measured_at,
                            stored_sample.soil_moisture.raw_adc,
                            stored_sample.soil_moisture.percent,
                            None,
                        ),
                        (
                            stored_sample.id,
                            rain_sensor,
                            rain_calibration,
                            stored_sample.measured_at,
                            stored_sample.rain.raw_adc,
                            stored_sample.rain.wetness_percent,
                            stored_sample.rain.detected,
                        ),
                    ],
                )
                if stored_sample.quality_flags:
                    connection.cursor().executemany(
                        """
                        INSERT INTO sample_quality_flags(sample_id, flag_code)
                        VALUES (%s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        [
                            (stored_sample.id, flag)
                            for flag in stored_sample.quality_flags
                        ],
                    )
        return stored_sample, True

    def list_samples(
        self,
        *,
        limit: int,
        device_id: str | None = None,
        group_id: str | None = None,
        from_at: datetime | None = None,
        to_at: datetime | None = None,
        variable: str | None = None,
        min_value: float | None = None,
        max_value: float | None = None,
    ) -> list[TelemetrySample]:
        clauses: list[str] = []
        parameters: list[Any] = []
        if device_id:
            clauses.append("device_id = %s")
            parameters.append(device_id)
        if group_id:
            clauses.append("group_id = %s")
            parameters.append(group_id)
        if from_at:
            clauses.append("measured_at >= %s")
            parameters.append(_as_utc(from_at))
        if to_at:
            clauses.append("measured_at <= %s")
            parameters.append(_as_utc(to_at))
        if variable:
            column = _FILTER_COLUMNS.get(variable)
            if column is None:
                raise ValueError(f"Variable de filtro no soportada: {variable}")
            if min_value is not None:
                clauses.append(f"{column} >= %s")
                parameters.append(min_value)
            if max_value is not None:
                clauses.append(f"{column} <= %s")
                parameters.append(max_value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        parameters.append(limit)
        with self._database.pool.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM vw_telemetry_wide
                {where}
                ORDER BY measured_at DESC, id DESC
                LIMIT %s
                """,
                parameters,
            ).fetchall()
        return [_from_row(row) for row in rows]

    def list_device_ids(self) -> list[str]:
        with self._database.pool.connection() as connection:
            rows = connection.execute(
                "SELECT external_id FROM devices WHERE active ORDER BY external_id"
            ).fetchall()
        return [str(row["external_id"]) for row in rows]

    def list_group_ids(self) -> list[str]:
        with self._database.pool.connection() as connection:
            rows = connection.execute(
                "SELECT code FROM iot_groups ORDER BY code"
            ).fetchall()
        return [str(row["code"]) for row in rows]

    @staticmethod
    def _get_sensor(
        connection,
        *,
        device_uuid: Any,
        sensor_type: str,
    ) -> tuple[Any, Any | None]:
        row = connection.execute(
            """
            SELECT sensor.id AS sensor_id, calibration.id AS calibration_id
            FROM sensors sensor
            JOIN sensor_types type ON type.id = sensor.sensor_type_id
            LEFT JOIN LATERAL (
                SELECT item.id
                FROM calibrations item
                WHERE item.sensor_id = sensor.id
                  AND item.valid_from <= now()
                  AND (item.valid_to IS NULL OR item.valid_to > now())
                ORDER BY item.version DESC
                LIMIT 1
            ) calibration ON TRUE
            WHERE sensor.device_id = %s
              AND type.code = %s
              AND sensor.active
            ORDER BY sensor.installed_at DESC
            LIMIT 1
            """,
            (device_uuid, sensor_type),
        ).fetchone()
        if row is None:
            raise RuntimeError(
                f"El dispositivo registrado no tiene sensor activo {sensor_type}."
            )
        return row["sensor_id"], row["calibration_id"]

    @staticmethod
    def _find_by_device_sequence(connection, device_id: str, sequence: int):
        return connection.execute(
            """
            SELECT wide.*
            FROM vw_telemetry_wide wide
            WHERE wide.device_id = %s AND wide.sequence = %s
            """,
            (device_id, sequence),
        ).fetchone()


def _from_row(row: dict[str, Any]) -> TelemetrySample:
    return TelemetrySample(
        id=str(row["id"]),
        schema_version=str(row["schema_version"]),
        group_id=str(row["group_id"]),
        device_id=str(row["device_id"]),
        sequence=int(row["sequence"]),
        measured_at=_as_utc(row["measured_at"]),
        received_at=_as_utc(row["received_at"]),
        sampling_period_seconds=int(row["sampling_period_seconds"]),
        soil_moisture=SoilMoistureReading(
            raw_adc=int(row["soil_raw_adc"]),
            percent=float(row["soil_moisture_percent"]),
        ),
        rain=RainReading(
            raw_adc=int(row["rain_raw_adc"]),
            wetness_percent=float(row["rain_wetness_percent"]),
            detected=bool(row["rain_detected"]),
        ),
        quality_flags=tuple(row["quality_flags"] or ()),
        soil_status=str(row["soil_status"]),
        rain_status=str(row["rain_status"]),
        device_alias=_optional_string(row.get("device_alias")),
        inserted_by_alias=_optional_string(row.get("inserted_by_alias")),
        ingest_credential_id=_optional_string(row.get("ingest_credential_id")),
    )


def _payload_fingerprint(sample: TelemetrySample) -> str:
    canonical = {
        "schema_version": sample.schema_version,
        "group_id": sample.group_id,
        "device_id": sample.device_id,
        "sequence": sample.sequence,
        "measured_at": _as_utc(sample.measured_at).isoformat(),
        "sampling_period_seconds": sample.sampling_period_seconds,
        "soil_raw_adc": sample.soil_moisture.raw_adc,
        "soil_percent": sample.soil_moisture.percent,
        "rain_raw_adc": sample.rain.raw_adc,
        "rain_wetness_percent": sample.rain.wetness_percent,
        "rain_detected": sample.rain.detected,
    }
    encoded = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _optional_string(value: Any) -> str | None:
    return None if value is None else str(value)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
