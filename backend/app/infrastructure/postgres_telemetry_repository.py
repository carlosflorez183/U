"""Adaptador PostgreSQL/TimescaleDB para telemetría ambiental DHT22."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from app.application.errors import AuthenticationError, AuthorizationError
from app.domain.telemetry import (
    AmbientReading,
    PendingTelemetrySample,
    TelemetrySample,
)
from app.infrastructure.database import PostgresDatabase

_FILTER_COLUMNS = {
    "temperature": "temperature_celsius",
    "humidity": "humidity_percent",
    # Compat con filtros antiguos.
    "soil_percent": "humidity_percent",
    "rain_percent": "humidity_percent",
    "soil_adc": "temperature_celsius",
    "rain_adc": "humidity_percent",
}


class PostgresTelemetryRepository:
    """Revalida identidad y persiste una muestra sin auto-crear dispositivos."""

    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def save(self, sample: PendingTelemetrySample) -> tuple[TelemetrySample, bool]:
        if not sample.ingest_credential_id:
            raise AuthenticationError("La muestra no tiene una credencial autenticada.")
        received_payload = _canonical_payload(sample)
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
                    FOR UPDATE OF device
                    FOR SHARE OF credential
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

                for candidate in self._find_payload_candidates(
                    connection,
                    identity["device_uuid"],
                    sample.measured_at,
                ):
                    try:
                        existing_sample = _from_row(candidate)
                    except (KeyError, ValueError, TypeError):
                        continue
                    if _canonical_payload(existing_sample) == received_payload:
                        return existing_sample, False

                next_sequence = self._next_sequence(
                    connection,
                    identity["device_uuid"],
                )
                stored_pending = replace(
                    sample,
                    device_alias=str(identity["device_alias"]),
                    inserted_by_alias=str(identity["credential_alias"]),
                    ingest_credential_id=str(identity["credential_id"]),
                )
                stored_sample = TelemetrySample.from_pending(
                    stored_pending,
                    sequence=next_sequence,
                )
                fingerprint = _payload_fingerprint(stored_pending)
                connection.execute(
                    "UPDATE devices SET last_seen_at = %s WHERE id = %s",
                    (stored_sample.received_at, identity["device_uuid"]),
                )
                # Nuevo esquema DHT22; fallback al esquema suelo/lluvia si 004 aún no corrió.
                try:
                    connection.execute(
                        """
                        INSERT INTO telemetry_samples(
                            id, device_id, sequence, schema_version, measured_at,
                            received_at, sampling_period_seconds, temp_status, humidity_status,
                            ingest_credential_id, device_alias_at_ingest,
                            credential_alias_at_ingest, payload_sha256
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s
                        )
                        """,
                        (
                            stored_sample.id,
                            identity["device_uuid"],
                            stored_sample.sequence,
                            stored_sample.schema_version,
                            stored_sample.measured_at,
                            stored_sample.received_at,
                            stored_sample.sampling_period_seconds,
                            stored_sample.temp_status,
                            stored_sample.humidity_status,
                            identity["credential_id"],
                            identity["device_alias"],
                            identity["credential_alias"],
                            fingerprint,
                        ),
                    )
                except Exception:
                    connection.execute(
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
                        """,
                        (
                            stored_sample.id,
                            identity["device_uuid"],
                            stored_sample.sequence,
                            stored_sample.schema_version,
                            stored_sample.measured_at,
                            stored_sample.received_at,
                            stored_sample.sampling_period_seconds,
                            stored_sample.humidity_status,
                            "RAIN_DETECTED"
                            if stored_sample.ambient.humidity_percent >= 70.0
                            else "NO_RAIN",
                            identity["credential_id"],
                            identity["device_alias"],
                            identity["credential_alias"],
                            fingerprint,
                        ),
                    )

                temp_sensor, temp_cal = self._get_sensor_flexible(
                    connection,
                    device_uuid=identity["device_uuid"],
                    candidates=("temperature", "soil_moisture"),
                )
                hum_sensor, hum_cal = self._get_sensor_flexible(
                    connection,
                    device_uuid=identity["device_uuid"],
                    candidates=("humidity", "rain_wetness"),
                )
                # raw_adc NULL para DHT22 (sin ADC). Requiere migración 004;
                # si la columna sigue NOT NULL, se guarda 0 como compat.
                try:
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
                                temp_sensor,
                                temp_cal,
                                stored_sample.measured_at,
                                None,
                                stored_sample.ambient.temperature_celsius,
                                None,
                            ),
                            (
                                stored_sample.id,
                                hum_sensor,
                                hum_cal,
                                stored_sample.measured_at,
                                None,
                                stored_sample.ambient.humidity_percent,
                                None,
                            ),
                        ],
                    )
                except Exception:
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
                                temp_sensor,
                                temp_cal,
                                stored_sample.measured_at,
                                0,
                                stored_sample.ambient.temperature_celsius
                                if stored_sample.ambient.temperature_celsius >= 0
                                else 0,
                                None,
                            ),
                            (
                                stored_sample.id,
                                hum_sensor,
                                hum_cal,
                                stored_sample.measured_at,
                                0,
                                stored_sample.ambient.humidity_percent,
                                stored_sample.ambient.humidity_percent >= 70.0,
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
        samples: list[TelemetrySample] = []
        for row in rows:
            try:
                samples.append(_from_row(row))
            except (KeyError, ValueError, TypeError):
                continue
        return samples

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
        return PostgresTelemetryRepository._get_sensor_flexible(
            connection, device_uuid=device_uuid, candidates=(sensor_type,)
        )

    @staticmethod
    def _get_sensor_flexible(
        connection,
        *,
        device_uuid: Any,
        candidates: tuple[str, ...],
    ) -> tuple[Any, Any | None]:
        for sensor_type in candidates:
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
            if row is not None:
                return row["sensor_id"], row["calibration_id"]
        raise RuntimeError(
            f"El dispositivo registrado no tiene sensor activo {candidates}."
        )

    @staticmethod
    def _find_payload_candidates(connection, device_uuid: Any, measured_at: datetime):
        return connection.execute(
            """
            SELECT wide.*
            FROM vw_telemetry_wide wide
            WHERE wide.id IN (
                SELECT sample.id
                FROM telemetry_samples sample
                WHERE sample.device_id = %s
                  AND sample.measured_at = %s
            )
            ORDER BY wide.sequence, wide.id
            """,
            (device_uuid, measured_at),
        ).fetchall()

    @staticmethod
    def _next_sequence(connection, device_uuid: Any) -> int:
        row = connection.execute(
            """
            SELECT MAX(sequence) AS max_sequence
            FROM telemetry_samples
            WHERE device_id = %s
            """,
            (device_uuid,),
        ).fetchone()
        maximum = row["max_sequence"]
        if maximum is None:
            return 0
        maximum = int(maximum)
        if maximum >= 9_223_372_036_854_775_807:
            raise RuntimeError("El dispositivo agotó el rango disponible de secuencias.")
        return maximum + 1


def _from_row(row: dict[str, Any]) -> TelemetrySample:
    # Nuevo esquema DHT22; fallback al esquema suelo/lluvia.
    if "temperature_celsius" in row and "humidity_percent" in row:
        ambient = AmbientReading(
            temperature_celsius=float(row["temperature_celsius"]),
            humidity_percent=float(row["humidity_percent"]),
        )
        temp_status = str(row.get("temp_status") or "COMFORT")
        humidity_status = str(row.get("humidity_status") or "COMFORT")
    else:
        ambient = AmbientReading(
            temperature_celsius=22.0,
            humidity_percent=float(row["soil_moisture_percent"]),
        )
        temp_status = "COMFORT"
        humidity_status = str(row.get("soil_status") or "COMFORT")
    return TelemetrySample(
        id=str(row["id"]),
        schema_version=str(row["schema_version"]),
        group_id=str(row["group_id"]),
        device_id=str(row["device_id"]),
        sequence=int(row["sequence"]),
        measured_at=_as_utc(row["measured_at"]),
        received_at=_as_utc(row["received_at"]),
        sampling_period_seconds=int(row["sampling_period_seconds"]),
        ambient=ambient,
        quality_flags=tuple(row["quality_flags"] or ()),
        temp_status=temp_status,
        humidity_status=humidity_status,
        device_alias=_optional_string(row.get("device_alias")),
        inserted_by_alias=_optional_string(row.get("inserted_by_alias")),
        ingest_credential_id=_optional_string(row.get("ingest_credential_id")),
    )


def _canonical_payload(
    sample: PendingTelemetrySample | TelemetrySample,
) -> dict[str, Any]:
    """Campos de entrada que identifican un reintento, sin sequence ni credenciales."""
    ambient = sample.ambient if isinstance(sample, TelemetrySample) else sample.ambient
    # Compat: TelemetrySample antiguo exponía soil_moisture/rain vía properties.
    if not isinstance(ambient, AmbientReading):
        raise ValueError("Muestra sin bloque ambient.")
    return {
        "schema_version": sample.schema_version,
        "group_id": sample.group_id,
        "device_id": sample.device_id,
        "measured_at": _as_utc(sample.measured_at).isoformat(),
        "sampling_period_seconds": sample.sampling_period_seconds,
        "temperature_celsius": float(ambient.temperature_celsius),
        "humidity_percent": float(ambient.humidity_percent),
    }


def _payload_fingerprint(sample: PendingTelemetrySample | TelemetrySample) -> str:
    canonical = _canonical_payload(sample)
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
