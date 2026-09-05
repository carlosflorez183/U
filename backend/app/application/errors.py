"""Errores de aplicación que se traducen a respuestas HTTP seguras."""


class AuthenticationError(Exception):
    """Las credenciales no se pudieron verificar."""


class AuthorizationError(Exception):
    """La identidad existe, pero no puede ejecutar la operación."""


class ResourceConflictError(Exception):
    """La operación colisiona con un recurso o secuencia existente."""


class ResourceNotFoundError(Exception):
    """El recurso administrativo no existe."""
