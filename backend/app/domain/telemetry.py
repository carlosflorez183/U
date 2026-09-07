"""Modelo de dominio para telemetría agrícola IoT."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class SoilMoistureReading:
    """Lectura del sensor capacitivo de humedad del suelo."""

    raw_adc: int
    percent: float

    def __post_init__(self) -> None:
        _validate_adc(self.raw_adc, "soil_moisture.raw_adc")
        _validate_percent(self.percent, "soil_moisture.percent")


@dataclass(frozen=True, slots=True)
class RainReading:
    """Humedad superficial detectada por la placa de lluvia."""

    raw_adc: int
    wetness_percent: float
    detected: bool

    def __post_init__(self) -> None:
        _validate_adc(self.raw_adc, "rain.raw_adc")
        _validate_percent(self.wetness_percent, "rain.wetness_percent")


@dataclass(frozen=True, slots=True)
class PendingTelemetrySample:
    """Muestra validada aún sin la secuencia autoritativa del servidor."""

    schema_version: str
    group_id: str
    device_id: str
    measured_at: datetime
    sampling_period_seconds: int
    soil_moisture: SoilMoistureReading
    rain: RainReading
    device_alias: str
    inserted_by_alias: str
    ingest_credential_id: str

    @classmethod
    def create(
        cls,
        *,
        schema_version: str,
        group_id: str,
        device_id: str,
        measured_at: datetime,
        sampling_period_seconds: int,
        soil_moisture: SoilMoistureReading,
        rain: RainReading,
        device_alias: str,
        inserted_by_alias: str,
        ingest_credential_id: str,
    ) -> "PendingTelemetrySample":
        if schema_version != "2.0":
            raise ValueError("schema_version debe ser '2.0'.")
        if not group_id.strip() or not device_id.strip():
            raise ValueError("group_id y device_id son obligatorios.")
        if not device_alias.strip() or not inserted_by_alias.strip():
            raise ValueError("Los alias de dispositivo y credencial son obligatorios.")
        if not ingest_credential_id.strip():
            raise ValueError("La credencial de ingesta es obligatoria.")
        if sampling_period_seconds not in {5, 10}:
            raise ValueError("sampling_period_seconds debe ser 5 o 10.")
        if measured_at.tzinfo is None or measured_at.utcoffset() is None:
            raise ValueError("measured_at debe incluir zona horaria.")
        return cls(
            schema_version=schema_version,
            group_id=group_id.strip(),
            device_id=device_id.strip(),
            measured_at=measured_at.astimezone(timezone.utc),
            sampling_period_seconds=sampling_period_seconds,
            soil_moisture=soil_moisture,
            rain=rain,
            device_alias=device_alias.strip(),
            inserted_by_alias=inserted_by_alias.strip(),
            ingest_credential_id=ingest_credential_id,
        )


@dataclass(frozen=True, slots=True)
class TelemetrySample:
    """Muestra persistida con secuencia asignada por el servidor."""

    id: str
    schema_version: str
    group_id: str
    device_id: str
    sequence: int
    measured_at: datetime
    received_at: datetime
    sampling_period_seconds: int
    soil_moisture: SoilMoistureReading
    rain: RainReading
    quality_flags: tuple[str, ...]
    soil_status: str
    rain_status: str
    device_alias: str | None = None
    inserted_by_alias: str | None = None
    ingest_credential_id: str | None = None

    @classmethod
    def from_pending(
        cls,
        pending: PendingTelemetrySample,
        *,
        sequence: int,
    ) -> "TelemetrySample":
        if sequence < 0:
            raise ValueError("sequence debe ser mayor o igual a cero.")
        received_at = datetime.now(timezone.utc)
        return cls(
            id=str(uuid4()),
            schema_version=pending.schema_version,
            group_id=pending.group_id,
            device_id=pending.device_id,
            sequence=sequence,
            measured_at=pending.measured_at,
            received_at=received_at,
            sampling_period_seconds=pending.sampling_period_seconds,
            soil_moisture=pending.soil_moisture,
            rain=pending.rain,
            quality_flags=_quality_flags(
                pending.measured_at,
                received_at,
                pending.soil_moisture,
                pending.rain,
            ),
            soil_status=_soil_status(pending.soil_moisture.percent),
            rain_status="RAIN_DETECTED" if pending.rain.detected else "NO_RAIN",
            device_alias=pending.device_alias,
            inserted_by_alias=pending.inserted_by_alias,
            ingest_credential_id=pending.ingest_credential_id,
        )

    @classmethod
    def create(
        cls,
        *,
        schema_version: str,
        group_id: str,
        device_id: str,
        sequence: int,
        measured_at: datetime,
        sampling_period_seconds: int,
        soil_moisture: SoilMoistureReading,
        rain: RainReading,
        device_alias: str,
        inserted_by_alias: str,
        ingest_credential_id: str,
    ) -> "TelemetrySample":
        """Compatibilidad para construir entidades persistidas en utilidades existentes."""
        pending = PendingTelemetrySample.create(
            schema_version=schema_version,
            group_id=group_id,
            device_id=device_id,
            measured_at=measured_at,
            sampling_period_seconds=sampling_period_seconds,
            soil_moisture=soil_moisture,
            rain=rain,
            device_alias=device_alias,
            inserted_by_alias=inserted_by_alias,
            ingest_credential_id=ingest_credential_id,
        )
        return cls.from_pending(pending, sequence=sequence)


def _validate_adc(value: int, field: str) -> None:
    if not 0 <= value <= 4095:
        raise ValueError(f"{field} debe estar entre 0 y 4095.")


def _validate_percent(value: float, field: str) -> None:
    if not 0 <= value <= 100:
        raise ValueError(f"{field} debe estar entre 0 y 100.")


def _soil_status(percent: float) -> str:
    if percent < 30:
        return "DRY"
    if percent <= 70:
        return "OPTIMAL"
    return "WET"


def _quality_flags(
    measured_at: datetime,
    received_at: datetime,
    soil: SoilMoistureReading,
    rain: RainReading,
) -> tuple[str, ...]:
    flags: list[str] = []
    if soil.raw_adc <= 5 or soil.raw_adc >= 4090:
        flags.append("SOIL_ADC_RAIL")
    if rain.raw_adc <= 5 or rain.raw_adc >= 4090:
        flags.append("RAIN_ADC_RAIL")
    if measured_at > received_at + timedelta(minutes=2):
        flags.append("TIMESTAMP_FUTURE")
    if measured_at < received_at - timedelta(days=1):
        flags.append("STALE_SAMPLE")
    if rain.detected != (rain.wetness_percent >= 10):
        flags.append("RAIN_DETECTION_MISMATCH")
    return tuple(flags)
