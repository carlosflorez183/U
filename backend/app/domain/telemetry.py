"""Modelo de dominio para telemetría ambiental IoT (DHT22)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class AmbientReading:
    """Lectura DHT22: temperatura del aire y humedad relativa.

    Sin ADC. Rangos hoja de datos AM2302: -40..80 °C, 0..100 %HR.
    """

    temperature_celsius: float
    humidity_percent: float

    def __post_init__(self) -> None:
        _validate_temperature(
            self.temperature_celsius, "ambient.temperature_celsius"
        )
        _validate_percent(self.humidity_percent, "ambient.humidity_percent")


@dataclass(frozen=True, slots=True)
class SoilMoistureReading:
    """Compatibilidad: antes suelo capacitivo con ADC."""

    raw_adc: int = 0
    percent: float = 0.0

    def __post_init__(self) -> None:
        _validate_adc(self.raw_adc, "soil_moisture.raw_adc")
        _validate_percent(self.percent, "soil_moisture.percent")


@dataclass(frozen=True, slots=True)
class RainReading:
    """Compatibilidad: antes sensor de lluvia con ADC."""

    raw_adc: int = 0
    wetness_percent: float = 0.0
    detected: bool = False

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
    ambient: AmbientReading
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
        ambient: AmbientReading | None = None,
        soil_moisture: SoilMoistureReading | AmbientReading | None = None,
        rain: RainReading | AmbientReading | None = None,
        temperature_celsius: float | None = None,
        humidity_percent: float | None = None,
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
        if sampling_period_seconds not in {5, 10, 20, 25, 30}:
            raise ValueError("sampling_period_seconds debe ser 5, 10, 20, 25 o 30.")
        if measured_at.tzinfo is None or measured_at.utcoffset() is None:
            raise ValueError("measured_at debe incluir zona horaria.")
        resolved = _resolve_ambient(
            ambient=ambient,
            soil_moisture=soil_moisture,
            rain=rain,
            temperature_celsius=temperature_celsius,
            humidity_percent=humidity_percent,
        )
        return cls(
            schema_version=schema_version,
            group_id=group_id.strip(),
            device_id=device_id.strip(),
            measured_at=measured_at.astimezone(timezone.utc),
            sampling_period_seconds=sampling_period_seconds,
            ambient=resolved,
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
    ambient: AmbientReading
    quality_flags: tuple[str, ...]
    temp_status: str
    humidity_status: str
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
            ambient=pending.ambient,
            quality_flags=_quality_flags(
                pending.measured_at,
                received_at,
                pending.ambient,
            ),
            temp_status=_temp_status(pending.ambient.temperature_celsius),
            humidity_status=_humidity_status(pending.ambient.humidity_percent),
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
        ambient: AmbientReading | None = None,
        soil_moisture=None,
        rain=None,
        temperature_celsius: float | None = None,
        humidity_percent: float | None = None,
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
            ambient=ambient,
            soil_moisture=soil_moisture,
            rain=rain,
            temperature_celsius=temperature_celsius,
            humidity_percent=humidity_percent,
            device_alias=device_alias,
            inserted_by_alias=inserted_by_alias,
            ingest_credential_id=ingest_credential_id,
        )
        return cls.from_pending(pending, sequence=sequence)

    # ---- Compatibilidad con código anterior suelo/lluvia ----
    @property
    def soil_moisture(self) -> SoilMoistureReading:
        return SoilMoistureReading(raw_adc=0, percent=self.ambient.humidity_percent)

    @property
    def rain(self) -> RainReading:
        hum = self.ambient.humidity_percent
        return RainReading(raw_adc=0, wetness_percent=hum, detected=hum >= 70.0)

    @property
    def soil_status(self) -> str:
        return self.humidity_status

    @property
    def rain_status(self) -> str:
        return "RAIN_DETECTED" if self.ambient.humidity_percent >= 70.0 else "NO_RAIN"


def _resolve_ambient(
    *,
    ambient: AmbientReading | None,
    soil_moisture=None,
    rain=None,
    temperature_celsius: float | None,
    humidity_percent: float | None,
) -> AmbientReading:
    if ambient is not None:
        if not isinstance(ambient, AmbientReading):
            raise ValueError("ambient debe ser AmbientReading.")
        return ambient
    if temperature_celsius is not None and humidity_percent is not None:
        return AmbientReading(
            temperature_celsius=float(temperature_celsius),
            humidity_percent=float(humidity_percent),
        )
    # Compat: si llega soil_moisture.percent como humedad y rain.wetness como respaldo,
    # o dicts legacy, intentar mapear a ambient. La temperatura legacy no existe,
    # se exige el nuevo contrato salvo que se provea temperature_celsius.
    raise ValueError(
        "Se requiere el bloque 'ambient' con temperature_celsius y humidity_percent."
    )


def _validate_adc(value: int, field: str) -> None:
    if not 0 <= value <= 4095:
        raise ValueError(f"{field} debe estar entre 0 y 4095.")


def _validate_percent(value: float, field: str) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{field} debe ser numérico.")
    if not 0 <= float(value) <= 100:
        raise ValueError(f"{field} debe estar entre 0 y 100.")


def _validate_temperature(value: float, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} debe ser numérico.")
    if not -40 <= float(value) <= 80:
        raise ValueError(f"{field} debe estar entre -40 y 80 °C.")


def _temp_status(celsius: float) -> str:
    if celsius < 18:
        return "COLD"
    if celsius <= 28:
        return "COMFORT"
    return "HOT"


def _humidity_status(percent: float) -> str:
    if percent < 30:
        return "DRY"
    if percent <= 70:
        return "COMFORT"
    return "HUMID"


def _soil_status(percent: float) -> str:
    return _humidity_status(percent)


def _quality_flags(
    measured_at: datetime,
    received_at: datetime,
    ambient: AmbientReading,
) -> tuple[str, ...]:
    flags: list[str] = []
    if measured_at > received_at + timedelta(minutes=2):
        flags.append("TIMESTAMP_FUTURE")
    if measured_at < received_at - timedelta(days=1):
        flags.append("STALE_SAMPLE")
    return tuple(flags)
