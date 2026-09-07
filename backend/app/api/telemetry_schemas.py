"""DTOs HTTP estrictos para la API de telemetría IoT."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.telemetry import TelemetrySample

IDENTIFIER_PATTERN = r"^[a-zA-Z0-9][a-zA-Z0-9_-]{1,63}$"
_MAX_BIGINT = 9_223_372_036_854_775_807
_STRICT_INPUT_CONFIG = ConfigDict(
    extra="forbid",
    strict=True,
    allow_inf_nan=False,
)


class SoilMoistureRequest(BaseModel):
    model_config = _STRICT_INPUT_CONFIG

    raw_adc: int = Field(strict=True, ge=0, le=4095)
    percent: float = Field(strict=True, ge=0, le=100, allow_inf_nan=False)


class RainRequest(BaseModel):
    model_config = _STRICT_INPUT_CONFIG

    raw_adc: int = Field(strict=True, ge=0, le=4095)
    wetness_percent: float = Field(
        strict=True, ge=0, le=100, allow_inf_nan=False
    )
    detected: bool = Field(strict=True)


class TelemetryIngestRequest(BaseModel):
    """Contrato JSON enviado periódicamente por el ESP32."""

    model_config = _STRICT_INPUT_CONFIG

    schema_version: Literal["2.0"] = "2.0"
    group_id: str = Field(
        strict=True, min_length=2, max_length=64, pattern=IDENTIFIER_PATTERN
    )
    device_id: str = Field(
        strict=True, min_length=2, max_length=64, pattern=IDENTIFIER_PATTERN
    )
    sequence: int | None = Field(default=None, strict=True, ge=0, le=_MAX_BIGINT)
    measured_at: datetime
    sampling_period_seconds: Literal[5, 10]
    soil_moisture: SoilMoistureRequest
    rain: RainRequest

    @field_validator("measured_at", mode="before")
    @classmethod
    def parse_measured_at_iso(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("measured_at debe ser una fecha ISO-8601 válida.") from exc

    @field_validator("measured_at")
    @classmethod
    def measured_at_requires_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("measured_at debe incluir zona horaria, por ejemplo Z.")
        return value


class SoilMoistureResponse(BaseModel):
    raw_adc: int
    percent: float


class RainResponse(BaseModel):
    raw_adc: int
    wetness_percent: float
    detected: bool


class TelemetrySampleResponse(BaseModel):
    id: str
    schema_version: str
    group_id: str
    device_id: str
    sequence: int
    measured_at: datetime
    received_at: datetime
    sampling_period_seconds: int
    soil_moisture: SoilMoistureResponse
    rain: RainResponse
    quality_flags: list[str]
    soil_status: str
    rain_status: str
    device_alias: str | None = None
    inserted_by_alias: str | None = None
    ingest_credential_id: str | None = None
    duplicate: bool = False

    @classmethod
    def from_domain(
        cls, sample: TelemetrySample, *, duplicate: bool = False
    ) -> "TelemetrySampleResponse":
        return cls(
            id=sample.id,
            schema_version=sample.schema_version,
            group_id=sample.group_id,
            device_id=sample.device_id,
            sequence=sample.sequence,
            measured_at=sample.measured_at,
            received_at=sample.received_at,
            sampling_period_seconds=sample.sampling_period_seconds,
            soil_moisture=SoilMoistureResponse(
                raw_adc=sample.soil_moisture.raw_adc,
                percent=sample.soil_moisture.percent,
            ),
            rain=RainResponse(
                raw_adc=sample.rain.raw_adc,
                wetness_percent=sample.rain.wetness_percent,
                detected=sample.rain.detected,
            ),
            quality_flags=list(sample.quality_flags),
            soil_status=sample.soil_status,
            rain_status=sample.rain_status,
            device_alias=sample.device_alias,
            inserted_by_alias=sample.inserted_by_alias,
            ingest_credential_id=sample.ingest_credential_id,
            duplicate=duplicate,
        )
