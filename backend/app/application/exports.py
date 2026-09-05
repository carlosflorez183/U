"""Contratos de aplicación para exportar registros."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, Sequence

from app.domain.entities import Record
from app.domain.telemetry import TelemetrySample


class ExportFormat(str, Enum):
    """Formatos de descarga soportados por la aplicación."""

    CSV = "csv"
    JSON = "json"
    XLSX = "xlsx"
    PDF = "pdf"


@dataclass(frozen=True, slots=True)
class ExportedFile:
    """Archivo listo para ser entregado por un adaptador de entrada."""

    content: bytes
    filename: str
    media_type: str


class RecordExportRenderer(Protocol):
    """Puerto para convertir entidades de dominio a un archivo descargable."""

    def render(self, records: Sequence[Record], export_format: ExportFormat) -> ExportedFile:
        """Construye un archivo en el formato solicitado."""


class TelemetryExportRenderer(Protocol):
    """Puerto para exportar muestras IoT con columnas estables."""

    def render(
        self,
        samples: Sequence[TelemetrySample],
        export_format: ExportFormat,
    ) -> ExportedFile:
        """Construye un archivo de telemetría en el formato solicitado."""
