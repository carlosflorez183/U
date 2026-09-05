"""Entidades del dominio de registros."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class Record:
    """Información arbitraria recibida por la API y persistida como un registro."""

    id: str
    data: Mapping[str, Any]
    source: str | None
    created_at: datetime

    @classmethod
    def create(cls, *, data: Mapping[str, Any], source: str | None = None) -> "Record":
        """Crea un registro válido asignando identidad y fecha en UTC."""
        if not data:
            raise ValueError("El contenido del registro no puede estar vacío.")

        normalized_source = source.strip() if source else None
        return cls(
            id=str(uuid4()),
            data=dict(data),
            source=normalized_source or None,
            created_at=datetime.now(timezone.utc),
        )
