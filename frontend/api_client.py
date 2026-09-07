"""Cliente HTTP de Streamlit para la API agrícola IoT."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import requests


@dataclass(frozen=True, slots=True)
class ApiResponse:
    """Respuesta JSON junto con sus metadatos de transporte."""

    data: Any
    status_code: int
    request_id: str | None


class ApiError(RuntimeError):
    """Error público y estructurado al comunicarse con la API."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str = "API_ERROR",
        details: list[dict[str, Any]] | None = None,
        request_id: str | None = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = list(details or [])
        self.request_id = request_id
        context = [f"HTTP {status_code}" if status_code is not None else None, code]
        if request_id:
            context.append(f"request_id {request_id}")
        suffix = " · ".join(item for item in context if item)
        super().__init__(f"{message} ({suffix})" if suffix else message)


class RecordsApiClient:
    """Cliente de telemetría y compatibilidad temporal con API v1."""

    def __init__(self, base_url: str, timeout_seconds: int = 10) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._session = requests.Session()

    def ingest_telemetry(
        self,
        payload: dict[str, Any],
        *,
        api_key: str,
        secret_key: str,
    ) -> dict[str, Any]:
        return self.ingest_telemetry_with_metadata(
            payload,
            api_key=api_key,
            secret_key=secret_key,
        ).data

    def ingest_telemetry_with_metadata(
        self,
        payload: dict[str, Any],
        *,
        api_key: str,
        secret_key: str,
        request_id: str | None = None,
    ) -> ApiResponse:
        headers = {"X-API-Key": api_key, "X-Secret-Key": secret_key}
        if request_id:
            headers["X-Request-ID"] = request_id
        return self._request_with_metadata(
            "POST",
            "/api/v2/telemetry/samples",
            request_id=request_id,
            json=payload,
            headers=headers,
        )

    def list_telemetry(
        self,
        *,
        limit: int = 500,
        device_id: str | None = None,
        group_id: str | None = None,
        from_at: str | None = None,
        to_at: str | None = None,
        variable: str | None = None,
        min_value: float | None = None,
        max_value: float | None = None,
    ) -> list[dict[str, Any]]:
        params = _telemetry_params(
            limit=limit,
            device_id=device_id,
            group_id=group_id,
            from_at=from_at,
            to_at=to_at,
            variable=variable,
            min_value=min_value,
            max_value=max_value,
        )
        return self._request("GET", "/api/v2/telemetry/samples", params=params)

    def list_devices(self) -> list[str]:
        return self._request("GET", "/api/v2/telemetry/devices")

    def list_groups(self) -> list[str]:
        return self._request("GET", "/api/v2/telemetry/groups")

    def export_telemetry(
        self,
        export_format: str,
        *,
        limit: int = 500,
        device_id: str | None = None,
        group_id: str | None = None,
        from_at: str | None = None,
        to_at: str | None = None,
        variable: str | None = None,
        min_value: float | None = None,
        max_value: float | None = None,
    ) -> tuple[bytes, str, str]:
        params = _telemetry_params(
            limit=limit,
            device_id=device_id,
            group_id=group_id,
            from_at=from_at,
            to_at=to_at,
            variable=variable,
            min_value=min_value,
            max_value=max_value,
        )
        return self._download(
            f"/api/v2/telemetry/export/{export_format}", export_format, params
        )

    def register_device(
        self,
        *,
        group_id: str,
        device_id: str,
        alias: str,
        admin_api_key: str,
        admin_secret_key: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v2/admin/devices",
            json={"group_id": group_id, "device_id": device_id, "alias": alias},
            headers=_admin_headers(admin_api_key, admin_secret_key),
        )

    def list_managed_devices(
        self, *, admin_api_key: str, admin_secret_key: str
    ) -> list[dict[str, Any]]:
        return self._request(
            "GET",
            "/api/v2/admin/devices",
            headers=_admin_headers(admin_api_key, admin_secret_key),
        )

    def set_device_active(
        self,
        device_id: str,
        active: bool,
        *,
        admin_api_key: str,
        admin_secret_key: str,
    ) -> dict[str, Any]:
        action = "activate" if active else "deactivate"
        return self._request(
            "POST",
            f"/api/v2/admin/devices/{device_id}/{action}",
            headers=_admin_headers(admin_api_key, admin_secret_key),
        )

    def update_device_alias(
        self,
        device_id: str,
        alias: str,
        *,
        admin_api_key: str,
        admin_secret_key: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v2/admin/devices/{device_id}/alias",
            json={"alias": alias},
            headers=_admin_headers(admin_api_key, admin_secret_key),
        )

    def create_device_credential(
        self,
        *,
        device_id: str,
        alias: str,
        admin_api_key: str,
        admin_secret_key: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v2/admin/credentials",
            json={"device_id": device_id, "alias": alias},
            headers=_admin_headers(admin_api_key, admin_secret_key),
        )

    def list_device_credentials(
        self, *, admin_api_key: str, admin_secret_key: str
    ) -> list[dict[str, Any]]:
        return self._request(
            "GET",
            "/api/v2/admin/credentials",
            headers=_admin_headers(admin_api_key, admin_secret_key),
        )

    def revoke_device_credential(
        self,
        credential_id: str,
        *,
        admin_api_key: str,
        admin_secret_key: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v2/admin/credentials/{credential_id}/revoke",
            headers=_admin_headers(admin_api_key, admin_secret_key),
        )

    def create_record(self, data: dict[str, Any], source: str | None) -> dict[str, Any]:
        return self._request("POST", "/api/v1/records", json={"data": data, "source": source})

    def list_records(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._request("GET", "/api/v1/records", params={"limit": limit})

    def export_records(self, export_format: str, limit: int = 50) -> tuple[bytes, str, str]:
        return self._download(
            f"/api/v1/records/export/{export_format}", export_format, {"limit": limit}
        )

    def _download(
        self, path: str, export_format: str, params: dict[str, Any]
    ) -> tuple[bytes, str, str]:
        if export_format not in {"csv", "json", "xlsx", "pdf"}:
            raise ValueError(f"Formato no soportado: {export_format}")
        try:
            response = self._session.get(
                f"{self._base_url}{path}",
                params=params,
                timeout=max(self._timeout_seconds, 30),
            )
        except requests.RequestException as exc:
            raise ApiError(
                "No fue posible conectarse con la API para generar la exportación.",
                code="NETWORK_ERROR",
            ) from exc
        if not response.ok:
            raise _api_error_from_response(response)
        disposition = response.headers.get("Content-Disposition", "")
        filename_match = re.search(r'filename="?([^";]+)"?', disposition)
        filename = filename_match.group(1) if filename_match else f"telemetria.{export_format}"
        media_type = response.headers.get("Content-Type", "application/octet-stream")
        return response.content, filename, media_type

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        return self._request_with_metadata(method, path, **kwargs).data

    def _request_with_metadata(
        self,
        method: str,
        path: str,
        *,
        request_id: str | None = None,
        **kwargs: Any,
    ) -> ApiResponse:
        try:
            response = self._session.request(
                method,
                f"{self._base_url}{path}",
                timeout=self._timeout_seconds,
                **kwargs,
            )
        except requests.RequestException as exc:
            raise ApiError(
                "No fue posible conectarse con la API.",
                code="NETWORK_ERROR",
                request_id=request_id,
            ) from exc

        response_request_id = response.headers.get("X-Request-ID") or request_id
        if not response.ok:
            raise _api_error_from_response(response, fallback_request_id=response_request_id)
        try:
            data = response.json()
        except requests.JSONDecodeError as exc:
            raise ApiError(
                "La API devolvió una respuesta que no es JSON.",
                status_code=response.status_code,
                code="INVALID_RESPONSE",
                request_id=response_request_id,
            ) from exc
        return ApiResponse(
            data=data,
            status_code=response.status_code,
            request_id=response_request_id,
        )


def _api_error_from_response(
    response: requests.Response,
    *,
    fallback_request_id: str | None = None,
) -> ApiError:
    request_id = response.headers.get("X-Request-ID") or fallback_request_id
    code = "HTTP_ERROR"
    message = "La API rechazó la solicitud."
    details: list[dict[str, Any]] = []
    try:
        payload = response.json()
    except requests.JSONDecodeError:
        payload = None
    if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
        error = payload["error"]
        if isinstance(error.get("code"), str) and error["code"]:
            code = error["code"]
        if isinstance(error.get("message"), str) and error["message"]:
            message = error["message"]
        raw_details = error.get("details")
        if isinstance(raw_details, list):
            details = [item for item in raw_details if isinstance(item, dict)]
        if isinstance(error.get("request_id"), str) and error["request_id"]:
            request_id = error["request_id"]
    return ApiError(
        message,
        status_code=response.status_code,
        code=code,
        details=details,
        request_id=request_id,
    )


def _admin_headers(api_key: str, secret_key: str) -> dict[str, str]:
    return {
        "X-Admin-API-Key": api_key,
        "X-Admin-Secret-Key": secret_key,
    }


def _telemetry_params(**values: Any) -> dict[str, Any]:
    values["from"] = values.pop("from_at")
    values["to"] = values.pop("to_at")
    return _without_none(values)


def _without_none(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}
