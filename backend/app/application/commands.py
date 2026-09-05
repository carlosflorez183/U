"""Comandos que ingresan al contexto de aplicación."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from app.domain.auth import IngestPrincipal

_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{1,63}$")
_VARIABLE_RANGES: dict[str, tuple[float, float]] = {
    "soil_percent": (0.0, 100.0),
    "rain_percent": (0.0, 100.0),
    "soil_adc": (0.0, 4095.0),
    "rain_adc": (0.0, 4095.0),
}


@dataclass(frozen=True, slots=True)
class CreateRecordCommand:
    """Datos necesarios para registrar una nueva entrada."""

    data: Mapping[str, Any]
    source: str | None = None


@dataclass(frozen=True, slots=True)
class IngestTelemetryCommand:
    """Muestra tipada recibida desde un dispositivo ESP32."""

    schema_version: str
    group_id: str
    device_id: str
    sequence: int
    measured_at: datetime
    sampling_period_seconds: int
    soil_raw_adc: int
    soil_percent: float
    rain_raw_adc: int
    rain_wetness_percent: float
    rain_detected: bool
    principal: IngestPrincipal


@dataclass(frozen=True, slots=True)
class TelemetryQuery:
    """Filtros validados para consultar o exportar telemetría."""

    limit: int = 500
    device_id: str | None = None
    group_id: str | None = None
    from_at: datetime | None = None
    to_at: datetime | None = None
    variable: str | None = None
    min_value: float | None = None
    max_value: float | None = None

    def __post_init__(self) -> None:
        if type(self.limit) is not int or not 1 <= self.limit <= 5000:
            raise ValueError("limit debe ser un entero entre 1 y 5000.")

        for field_name, identifier in (
            ("device_id", self.device_id),
            ("group_id", self.group_id),
        ):
            if identifier is not None and (
                not isinstance(identifier, str)
                or _IDENTIFIER_PATTERN.fullmatch(identifier) is None
            ):
                raise ValueError(f"{field_name} no tiene un formato válido.")

        if self.variable is not None and self.variable not in _VARIABLE_RANGES:
            raise ValueError("La variable de filtro no está soportada.")
        if (self.min_value is not None or self.max_value is not None) and not self.variable:
            raise ValueError("variable es obligatoria al filtrar por rango de valores.")

        for field_name, value in (
            ("min_value", self.min_value),
            ("max_value", self.max_value),
        ):
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
            ):
                raise ValueError(f"{field_name} debe ser un número finito.")

        if (
            self.min_value is not None
            and self.max_value is not None
            and self.min_value > self.max_value
        ):
            raise ValueError("min_value no puede ser mayor que max_value.")

        if self.variable is not None:
            lower, upper = _VARIABLE_RANGES[self.variable]
            for field_name, value in (
                ("min_value", self.min_value),
                ("max_value", self.max_value),
            ):
                if value is not None and not lower <= float(value) <= upper:
                    raise ValueError(
                        f"{field_name} debe estar entre {lower:g} y {upper:g} para {self.variable}."
                    )

        for field_name, value in (("from", self.from_at), ("to", self.to_at)):
            if value is not None and (
                not isinstance(value, datetime)
                or value.tzinfo is None
                or value.utcoffset() is None
            ):
                raise ValueError(f"{field_name} debe ser una fecha con zona horaria.")
        if self.from_at and self.to_at and self.from_at > self.to_at:
            raise ValueError("La fecha inicial no puede ser posterior a la final.")
