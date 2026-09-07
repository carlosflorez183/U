"""Puertos de salida del dominio."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.domain.entities import Record
from app.domain.telemetry import PendingTelemetrySample, TelemetrySample


class RecordRepository(Protocol):
    """Contrato que debe cumplir cualquier almacenamiento de registros."""

    def save(self, record: Record) -> Record:
        """Guarda un registro y devuelve la entidad persistida."""

    def list_recent(self, limit: int) -> list[Record]:
        """Obtiene los registros más recientes."""


class TelemetryRepository(Protocol):
    """Puerto de persistencia para la serie temporal IoT."""

    def save(self, sample: PendingTelemetrySample) -> tuple[TelemetrySample, bool]:
        """Asigna sequence y guarda, o devuelve la existente si es un reintento."""

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
        """Consulta muestras recientes con filtros opcionales."""

    def list_device_ids(self) -> list[str]:
        """Lista los dispositivos que ya enviaron telemetría."""

    def list_group_ids(self) -> list[str]:
        """Lista los grupos que ya enviaron telemetría."""
