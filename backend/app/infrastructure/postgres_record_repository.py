"""Persistencia PostgreSQL para la API v1 compatible."""

from __future__ import annotations

from datetime import timezone

from psycopg.types.json import Jsonb

from app.domain.entities import Record
from app.infrastructure.database import PostgresDatabase


class PostgresRecordRepository:
    """Guarda registros heredados como JSONB sin contaminar el dominio."""

    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def save(self, record: Record) -> Record:
        with self._database.pool.connection() as connection:
            connection.execute(
                """
                INSERT INTO legacy_records (id, data, source, created_at)
                VALUES (%s, %s, %s, %s)
                """,
                (record.id, Jsonb(dict(record.data)), record.source, record.created_at),
            )
        return record

    def list_recent(self, limit: int) -> list[Record]:
        with self._database.pool.connection() as connection:
            rows = connection.execute(
                """
                SELECT id, data, source, created_at
                FROM legacy_records
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        return [
            Record(
                id=str(row["id"]),
                data=dict(row["data"]),
                source=row["source"],
                created_at=row["created_at"].astimezone(timezone.utc),
            )
            for row in rows
        ]
