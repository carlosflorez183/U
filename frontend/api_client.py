"""Cliente HTTP de Streamlit para la API agrícola IoT."""

from __future__ import annotations

import re
from typing import Any

import requests


class ApiError(RuntimeError):
    """Error controlado al comunicarse con la API."""


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
        return self._request(
            "POST",
            "/api/v2/telemetry/samples",
            json=payload,
            headers={"X-API-Key": api_key, "X-Secret-Key": secret_key},
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
            response.raise_for_status()
        except requests.RequestException as exc:
            detail = exc.response.text if exc.response is not None else str(exc)
            raise ApiError(f"No se pudo generar la exportación: {detail}") from exc
        disposition = response.headers.get("Content-Disposition", "")
        filename_match = re.search(r'filename="?([^";]+)"?', disposition)
        filename = filename_match.group(1) if filename_match else f"telemetria.{export_format}"
        media_type = response.headers.get("Content-Type", "application/octet-stream")
        return response.content, filename, media_type

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self._session.request(
                method,
                f"{self._base_url}{path}",
                timeout=self._timeout_seconds,
                **kwargs,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            detail = exc.response.text if exc.response is not None else str(exc)
            raise ApiError(f"No se pudo comunicar con la API: {detail}") from exc


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
