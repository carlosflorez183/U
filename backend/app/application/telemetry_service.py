"""Casos de uso para ingesta, consulta y exportación de telemetría."""

from __future__ import annotations

from app.application.commands import IngestTelemetryCommand, TelemetryQuery
from app.application.errors import AuthorizationError
from app.application.exports import ExportFormat, ExportedFile, TelemetryExportRenderer
from app.domain.repositories import TelemetryRepository
from app.domain.telemetry import (
    AmbientReading,
    PendingTelemetrySample,
    TelemetrySample,
)


class TelemetryService:
    """Orquesta telemetría sin depender de HTTP ni del motor PostgreSQL."""

    def __init__(
        self,
        repository: TelemetryRepository,
        export_renderer: TelemetryExportRenderer,
    ) -> None:
        self._repository = repository
        self._export_renderer = export_renderer

    def ingest(self, command: IngestTelemetryCommand) -> tuple[TelemetrySample, bool]:
        principal = command.principal
        if command.device_id != principal.device_id or command.group_id != principal.group_id:
            raise AuthorizationError(
                "La credencial no está autorizada para el grupo o dispositivo indicado."
            )
        sample = PendingTelemetrySample.create(
            schema_version=command.schema_version,
            group_id=command.group_id,
            device_id=command.device_id,
            measured_at=command.measured_at,
            sampling_period_seconds=command.sampling_period_seconds,
            ambient=AmbientReading(
                temperature_celsius=command.temperature_celsius,
                humidity_percent=command.humidity_percent,
            ),
            device_alias=principal.device_alias,
            inserted_by_alias=principal.credential_alias,
            ingest_credential_id=principal.credential_id,
        )
        return self._repository.save(sample)

    def list_samples(self, query: TelemetryQuery) -> list[TelemetrySample]:
        return self._repository.list_samples(
            limit=query.limit,
            device_id=query.device_id,
            group_id=query.group_id,
            from_at=query.from_at,
            to_at=query.to_at,
            variable=query.variable,
            min_value=query.min_value,
            max_value=query.max_value,
        )

    def list_device_ids(self) -> list[str]:
        return self._repository.list_device_ids()

    def list_group_ids(self) -> list[str]:
        return self._repository.list_group_ids()

    def export_samples(
        self, query: TelemetryQuery, export_format: ExportFormat
    ) -> ExportedFile:
        return self._export_renderer.render(self.list_samples(query), export_format)
