"""Orquestación de los casos de uso."""

from __future__ import annotations

from app.application.commands import CreateRecordCommand
from app.application.exports import ExportFormat, ExportedFile, RecordExportRenderer
from app.domain.entities import Record
from app.domain.repositories import RecordRepository


class RecordService:
    """Expone operaciones de aplicación sin conocer PostgreSQL ni HTTP."""

    def __init__(self, repository: RecordRepository, export_renderer: RecordExportRenderer) -> None:
        self._repository = repository
        self._export_renderer = export_renderer

    def create_record(self, command: CreateRecordCommand) -> Record:
        record = Record.create(data=command.data, source=command.source)
        return self._repository.save(record)

    def list_recent_records(self, limit: int) -> list[Record]:
        return self._repository.list_recent(limit=limit)

    def export_recent_records(self, export_format: ExportFormat, limit: int) -> ExportedFile:
        """Obtiene los registros más recientes y los convierte en un archivo."""
        records = self._repository.list_recent(limit=limit)
        return self._export_renderer.render(records, export_format)
