"""Caso de uso de analítica para el menú del teclado matricial."""

from __future__ import annotations

from typing import Any

from app.infrastructure.postgres_menu_repository import PostgresMenuRepository

# Umbral en °C/% para considerar que la serie "se mueve" entre horas consecutivas.
_TREND_THRESHOLD = 0.5


def _trend_label(current: Any, previous: Any) -> str:
    if current is None or previous is None:
        return "SIN_DATOS"
    delta = float(current) - float(previous)
    if delta > _TREND_THRESHOLD:
        return "SUBIENDO"
    if delta < -_TREND_THRESHOLD:
        return "BAJANDO"
    return "ESTABLE"


class MenuService:
    """Expone las siete consultas del menú como datos ya etiquetados."""

    def __init__(self, repository: PostgresMenuRepository) -> None:
        self._repository = repository

    def realtime(self, device_id: str | None) -> dict[str, Any] | None:
        return self._repository.realtime(device_id)

    def hourly_average(self, device_id: str | None) -> dict[str, Any]:
        return self._repository.hourly_average(device_id)

    def daily_extremes(self, device_id: str | None) -> dict[str, Any]:
        return self._repository.daily_extremes(device_id)

    def trend(self, device_id: str | None) -> dict[str, Any]:
        row = self._repository.trend(device_id)
        row["temperature_trend"] = _trend_label(
            row.get("temperature_now"), row.get("temperature_previous_hour")
        )
        row["humidity_trend"] = _trend_label(
            row.get("humidity_now"), row.get("humidity_previous_hour")
        )
        return row

    def outliers_today(self, device_id: str | None) -> dict[str, Any]:
        return self._repository.outliers_today(device_id)

    def active_alerts(self, device_id: str | None) -> dict[str, Any]:
        return self._repository.active_alerts(device_id)

    def connection_status(self, device_id: str | None) -> list[dict[str, Any]]:
        return self._repository.connection_status(device_id)
