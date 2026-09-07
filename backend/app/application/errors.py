"""Errores de aplicación que se traducen a respuestas HTTP seguras."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


class AuthenticationError(Exception):
    """Las credenciales no se pudieron verificar."""


class AuthorizationError(Exception):
    """La identidad existe, pero no puede ejecutar la operación."""


class ResourceConflictError(Exception):
    """La operación colisiona con un recurso o secuencia existente."""

    def __init__(
        self,
        message: str,
        *,
        details: Sequence[dict[str, Any]] | None = None,
        diagnostic_context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.details = [dict(item) for item in details or ()]
        self.diagnostic_context = dict(diagnostic_context or {})


class ResourceNotFoundError(Exception):
    """El recurso administrativo no existe."""
