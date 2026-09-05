"""Contrato uniforme y seguro de errores para HTTP y WebSocket."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Awaitable, Callable, Sequence
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from psycopg import Error as PostgresError
from psycopg import OperationalError
from psycopg_pool import PoolTimeout
from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.application.errors import (
    AuthenticationError,
    AuthorizationError,
    ResourceConflictError,
    ResourceNotFoundError,
)

logger = logging.getLogger("app.errors")

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
_JSON_METHODS = frozenset({"POST", "PUT", "PATCH"})


class RequestBodyTooLarge(Exception):
    """Señala que un cuerpo superó el límite antes de ser deserializado."""


class InvalidContentLength(Exception):
    """Señala una cabecera Content-Length inválida."""


def _request_id_from_scope(scope: Scope) -> str:
    candidate = Headers(scope=scope).get("x-request-id", "").strip()
    if _REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate
    return str(uuid4())


def _error_payload(
    *,
    code: str,
    message: str,
    request_id: str,
    details: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": list(details or []),
            "request_id": request_id,
        }
    }


def _request_id(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, str) and request_id:
        return request_id
    return str(uuid4())


def error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: Sequence[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Construye el único formato de error público de la API."""
    request_id = _request_id(request)
    response_headers = dict(headers or {})
    response_headers["X-Request-ID"] = request_id
    return JSONResponse(
        status_code=status_code,
        content=_error_payload(
            code=code,
            message=message,
            details=details,
            request_id=request_id,
        ),
        headers=response_headers,
    )


class ErrorHandlingMiddleware:
    """ASGI puro: correlación, límites y última barrera ante excepciones."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_telemetry_body_bytes: int,
        max_legacy_body_bytes: int,
    ) -> None:
        self.app = app
        self.max_telemetry_body_bytes = max_telemetry_body_bytes
        self.max_legacy_body_bytes = max_legacy_body_bytes

    def _body_limit(self, path: str) -> int | None:
        if path == "/api/v2/telemetry/samples":
            return self.max_telemetry_body_bytes
        if path.startswith("/api/v2/admin/"):
            return self.max_telemetry_body_bytes
        if path == "/api/v1/records":
            return self.max_legacy_body_bytes
        return None

    @staticmethod
    def _requires_json_body(path: str) -> bool:
        if path in {
            "/api/v2/telemetry/samples",
            "/api/v2/admin/devices",
            "/api/v2/admin/credentials",
            "/api/v1/records",
        }:
            return True
        return path.startswith("/api/v2/admin/devices/") and path.endswith(
            "/alias"
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket":
            await self._handle_websocket(scope, receive, send)
            return
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _request_id_from_scope(scope)
        scope.setdefault("state", {})["request_id"] = request_id
        started_at = time.perf_counter()
        response_started = False
        response_status = 500

        async def send_with_metadata(message: Message) -> None:
            nonlocal response_started, response_status
            if message["type"] == "http.response.start":
                response_started = True
                response_status = int(message["status"])
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
                headers["X-Process-Time-Ms"] = f"{(time.perf_counter() - started_at) * 1000:.2f}"
            await send(message)

        path = scope.get("path", "")
        limit = self._body_limit(path)
        try:
            if limit is not None and scope.get("method", "").upper() in _JSON_METHODS:
                self._validate_body_headers(
                    scope,
                    limit,
                    require_json=self._requires_json_body(path),
                )
                receive = self._limited_receive(receive, limit)
            await self.app(scope, receive, send_with_metadata)
        except StarletteHTTPException as exc:
            if not response_started:
                code, message = _HTTP_ERRORS.get(
                    exc.status_code,
                    ("BAD_REQUEST", "La solicitud no es válida."),
                )
                await self._send_error(
                    scope,
                    receive,
                    send_with_metadata,
                    status_code=exc.status_code,
                    code=code,
                    message=message,
                    request_id=request_id,
                )
        except InvalidContentLength:
            if not response_started:
                await self._send_error(
                    scope,
                    receive,
                    send_with_metadata,
                    status_code=400,
                    code="BAD_REQUEST",
                    message="La cabecera Content-Length no es válida.",
                    request_id=request_id,
                )
        except RequestBodyTooLarge:
            if not response_started:
                await self._send_error(
                    scope,
                    receive,
                    send_with_metadata,
                    status_code=413,
                    code="PAYLOAD_TOO_LARGE",
                    message="El cuerpo de la solicitud supera el límite permitido.",
                    request_id=request_id,
                )
        except Exception:
            logger.exception(
                "Error HTTP no controlado request_id=%s method=%s path=%s",
                request_id,
                scope.get("method"),
                scope.get("path"),
            )
            if response_started:
                raise
            await self._send_error(
                scope,
                receive,
                send_with_metadata,
                status_code=500,
                code="INTERNAL_ERROR",
                message="Ocurrió un error interno. Use el request_id para soporte.",
                request_id=request_id,
            )
        finally:
            logger.info(
                "HTTP request_id=%s method=%s path=%s status=%s duration_ms=%.2f",
                request_id,
                scope.get("method"),
                scope.get("path"),
                response_status,
                (time.perf_counter() - started_at) * 1000,
            )

    @staticmethod
    def _validate_body_headers(
        scope: Scope,
        limit: int,
        *,
        require_json: bool,
    ) -> None:
        headers = Headers(scope=scope)
        content_type = headers.get("content-type", "")
        media_type = content_type.split(";", maxsplit=1)[0].strip().lower()
        if require_json and media_type != "application/json" and not (
            media_type.startswith("application/") and media_type.endswith("+json")
        ):
            raise StarletteHTTPException(
                status_code=415,
                detail="El cuerpo debe enviarse como application/json.",
            )

        content_length = headers.get("content-length")
        if content_length is None:
            return
        try:
            parsed_length = int(content_length)
        except ValueError as exc:
            raise InvalidContentLength from exc
        if parsed_length < 0:
            raise InvalidContentLength
        if parsed_length > limit:
            raise RequestBodyTooLarge

    @staticmethod
    def _limited_receive(receive: Receive, limit: int) -> Receive:
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise RequestBodyTooLarge
            return message

        return limited_receive

    @staticmethod
    async def _send_error(
        scope: Scope,
        receive: Receive,
        send: Send,
        *,
        status_code: int,
        code: str,
        message: str,
        request_id: str,
    ) -> None:
        response = JSONResponse(
            status_code=status_code,
            content=_error_payload(
                code=code,
                message=message,
                request_id=request_id,
            ),
        )
        await response(scope, receive, send)

    async def _handle_websocket(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        request_id = _request_id_from_scope(scope)
        scope.setdefault("state", {})["request_id"] = request_id
        closed = False

        async def tracked_send(message: Message) -> None:
            nonlocal closed
            if message["type"] == "websocket.close":
                closed = True
            await send(message)

        try:
            await self.app(scope, receive, tracked_send)
        except Exception:
            logger.exception(
                "Error WebSocket no controlado request_id=%s path=%s",
                request_id,
                scope.get("path"),
            )
            if not closed:
                await send({"type": "websocket.close", "code": 1011})


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    details = [
        {
            "location": list(error.get("loc", ())),
            "message": str(error.get("msg", "Valor inválido.")),
            "type": str(error.get("type", "validation_error")),
        }
        for error in exc.errors()
    ]
    return error_response(
        request,
        status_code=422,
        code="VALIDATION_ERROR",
        message="Revise los campos indicados.",
        details=details,
    )


_HTTP_ERRORS: dict[int, tuple[str, str]] = {
    400: ("BAD_REQUEST", "La solicitud no es válida."),
    401: ("AUTHENTICATION_REQUIRED", "Las credenciales no son válidas."),
    403: ("FORBIDDEN", "La credencial no autoriza esta operación."),
    404: ("NOT_FOUND", "El recurso solicitado no existe."),
    405: ("METHOD_NOT_ALLOWED", "El método HTTP no está permitido."),
    409: ("CONFLICT", "La operación entra en conflicto con el estado actual."),
    413: ("PAYLOAD_TOO_LARGE", "El cuerpo supera el límite permitido."),
    415: ("UNSUPPORTED_MEDIA_TYPE", "El tipo de contenido no es compatible."),
    422: ("VALIDATION_ERROR", "Los datos proporcionados no son válidos."),
    503: ("DATABASE_UNAVAILABLE", "PostgreSQL no está disponible temporalmente."),
    504: ("UPSTREAM_TIMEOUT", "Un servicio dependiente excedió el tiempo de espera."),
}


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    code, message = _HTTP_ERRORS.get(
        exc.status_code,
        ("BAD_REQUEST" if exc.status_code < 500 else "INTERNAL_ERROR",
         "La solicitud no pudo procesarse." if exc.status_code < 500 else "Ocurrió un error interno."),
    )
    headers = dict(exc.headers or {})
    if exc.status_code == 503:
        headers.setdefault("Retry-After", "5")
    return error_response(
        request,
        status_code=exc.status_code,
        code=code,
        message=message,
        headers=headers,
    )


async def application_exception_handler(
    request: Request,
    exc: AuthenticationError | AuthorizationError | ResourceConflictError | ResourceNotFoundError,
) -> JSONResponse:
    mapping: dict[type[Exception], tuple[int, str, str]] = {
        AuthenticationError: (401, "AUTHENTICATION_REQUIRED", "Las credenciales no son válidas."),
        AuthorizationError: (403, "FORBIDDEN", "La credencial no autoriza esta operación."),
        ResourceConflictError: (409, "CONFLICT", "La operación entra en conflicto con el estado actual."),
        ResourceNotFoundError: (404, "NOT_FOUND", "El recurso solicitado no existe."),
    }
    status_code, code, message = mapping[type(exc)]
    headers = {"WWW-Authenticate": "ApiKey"} if status_code == 401 else None
    return error_response(
        request,
        status_code=status_code,
        code=code,
        message=message,
        headers=headers,
    )


async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    logger.info("Validación de dominio request_id=%s: %s", _request_id(request), exc)
    return error_response(
        request,
        status_code=422,
        code="VALIDATION_ERROR",
        message="Los datos proporcionados no son válidos.",
    )


async def database_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    logger.exception("Fallo PostgreSQL request_id=%s", _request_id(request), exc_info=exc)
    return error_response(
        request,
        status_code=503,
        code="DATABASE_UNAVAILABLE",
        message="PostgreSQL no está disponible temporalmente.",
        headers={"Retry-After": "5"},
    )


async def timeout_exception_handler(
    request: Request, exc: TimeoutError
) -> JSONResponse:
    logger.exception("Timeout request_id=%s", _request_id(request), exc_info=exc)
    return error_response(
        request,
        status_code=504,
        code="UPSTREAM_TIMEOUT",
        message="Un servicio dependiente excedió el tiempo de espera.",
    )


def install_exception_handlers(app: FastAPI) -> None:
    """Registra handlers tipados sin exponer SQL, entradas ni trazas."""
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(AuthenticationError, application_exception_handler)
    app.add_exception_handler(AuthorizationError, application_exception_handler)
    app.add_exception_handler(ResourceConflictError, application_exception_handler)
    app.add_exception_handler(ResourceNotFoundError, application_exception_handler)
    app.add_exception_handler(ValueError, value_error_handler)
    app.add_exception_handler(OperationalError, database_exception_handler)
    app.add_exception_handler(PoolTimeout, database_exception_handler)
    app.add_exception_handler(PostgresError, database_exception_handler)
    app.add_exception_handler(TimeoutError, timeout_exception_handler)
