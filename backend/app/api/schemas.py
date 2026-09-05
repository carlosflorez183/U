"""DTOs HTTP, separados de las entidades de dominio."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

_MAX_JSON_DEPTH = 32
_MAX_JSON_NODES = 10_000


def _validate_json_tree(value: Any, *, depth: int, counter: list[int]) -> None:
    """Impide valores no JSON, no finitos o estructuras patológicamente profundas."""
    counter[0] += 1
    if counter[0] > _MAX_JSON_NODES:
        raise ValueError(f"data no puede superar {_MAX_JSON_NODES} elementos JSON.")
    if depth > _MAX_JSON_DEPTH:
        raise ValueError(f"data no puede superar {_MAX_JSON_DEPTH} niveles.")

    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("data no admite números NaN o infinitos.")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_tree(item, depth=depth + 1, counter=counter)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("Todas las claves JSON de data deben ser texto.")
            _validate_json_tree(item, depth=depth + 1, counter=counter)
        return
    raise ValueError("data solo admite valores compatibles con JSON.")


class RecordCreateRequest(BaseModel):
    """Cuerpo JSONB compatible con v1, limitado y validado recursivamente."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    data: dict[str, Any] = Field(
        min_length=1,
        description="Objeto JSON no vacío a persistir.",
    )
    source: StrictStr | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Origen opcional del dato.",
    )

    @field_validator("data")
    @classmethod
    def data_must_be_safe_json(cls, value: dict[str, Any]) -> dict[str, Any]:
        _validate_json_tree(value, depth=0, counter=[0])
        return value

    @field_validator("source")
    @classmethod
    def source_must_not_have_outer_whitespace(cls, value: str | None) -> str | None:
        if value is not None and value != value.strip():
            raise ValueError("source no debe tener espacios al inicio o al final.")
        return value


class RecordResponse(BaseModel):
    """Representación pública de un registro guardado."""

    id: str
    data: dict[str, Any]
    source: str | None
    created_at: datetime
