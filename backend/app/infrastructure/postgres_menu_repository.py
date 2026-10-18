"""Consultas de analítica que alimentan el menú del teclado matricial."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.infrastructure.database import PostgresDatabase

# Línea base de Colombia (sin horario de verano) para el corte de "hoy".
_TODAY_START_SQL = (
    "date_trunc('day', now() AT TIME ZONE 'America/Bogota') "
    "AT TIME ZONE 'America/Bogota'"
)


class PostgresMenuRepository:
    """Lee las vistas de analítica (hypertable TimescaleDB) para el LCD."""

    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def realtime(self, device_id: str | None) -> dict[str, Any] | None:
        with self._database.pool.connection() as connection:
            row = connection.execute(
                f"""
                SELECT device_id, group_id, measured_at,
                       temperature_celsius, humidity_percent,
                       temp_status, humidity_status
                FROM vw_menu_realtime
                WHERE (%(device)s::text IS NULL OR device_id = %(device)s)
                ORDER BY measured_at DESC
                LIMIT 1
                """,
                {"device": device_id},
            ).fetchone()
        return None if row is None else dict(row)

    def hourly_average(self, device_id: str | None) -> dict[str, Any]:
        with self._database.pool.connection() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS sample_count,
                       AVG(temperature_celsius) AS avg_temperature_celsius,
                       AVG(humidity_percent) AS avg_humidity_percent
                FROM vw_telemetry_wide
                WHERE measured_at >= now() - INTERVAL '1 hour'
                  AND (%(device)s::text IS NULL OR device_id = %(device)s)
                """,
                {"device": device_id},
            ).fetchone()
        return dict(row)

    def daily_extremes(self, device_id: str | None) -> dict[str, Any]:
        with self._database.pool.connection() as connection:
            row = connection.execute(
                f"""
                SELECT COUNT(*) AS sample_count,
                       MIN(temperature_celsius) AS min_temperature_celsius,
                       MAX(temperature_celsius) AS max_temperature_celsius,
                       MIN(humidity_percent) AS min_humidity_percent,
                       MAX(humidity_percent) AS max_humidity_percent
                FROM vw_telemetry_wide
                WHERE measured_at >= {_TODAY_START_SQL}
                  AND (%(device)s::text IS NULL OR device_id = %(device)s)
                """,
                {"device": device_id},
            ).fetchone()
        return dict(row)

    def trend(self, device_id: str | None) -> dict[str, Any]:
        with self._database.pool.connection() as connection:
            row = connection.execute(
                """
                SELECT
                    AVG(temperature_celsius)
                        FILTER (WHERE measured_at >= now() - INTERVAL '1 hour')
                        AS temperature_now,
                    AVG(temperature_celsius)
                        FILTER (WHERE measured_at >= now() - INTERVAL '2 hours'
                                    AND measured_at < now() - INTERVAL '1 hour')
                        AS temperature_previous_hour,
                    AVG(humidity_percent)
                        FILTER (WHERE measured_at >= now() - INTERVAL '1 hour')
                        AS humidity_now,
                    AVG(humidity_percent)
                        FILTER (WHERE measured_at >= now() - INTERVAL '2 hours'
                                    AND measured_at < now() - INTERVAL '1 hour')
                        AS humidity_previous_hour,
                    STDDEV_POP(temperature_celsius)
                        FILTER (WHERE measured_at >= now() - INTERVAL '1 hour')
                        AS stddev_temperature_celsius,
                    STDDEV_POP(humidity_percent)
                        FILTER (WHERE measured_at >= now() - INTERVAL '1 hour')
                        AS stddev_humidity_percent,
                    COUNT(*) AS sample_count
                FROM vw_telemetry_wide
                WHERE measured_at >= now() - INTERVAL '2 hours'
                  AND (%(device)s::text IS NULL OR device_id = %(device)s)
                """,
                {"device": device_id},
            ).fetchone()
        return dict(row)

    def outliers_today(self, device_id: str | None) -> dict[str, Any]:
        with self._database.pool.connection() as connection:
            row = connection.execute(
                f"""
                SELECT COUNT(*) AS outlier_count,
                       COUNT(*) FILTER (
                           WHERE temperature_celsius < 18 OR temperature_celsius > 28
                       ) AS temperature_outlier_count,
                       COUNT(*) FILTER (
                           WHERE humidity_percent < 30 OR humidity_percent >= 70
                       ) AS humidity_outlier_count
                FROM vw_outliers
                WHERE measured_at >= {_TODAY_START_SQL}
                  AND (%(device)s::text IS NULL OR device_id = %(device)s)
                """,
                {"device": device_id},
            ).fetchone()
        return dict(row)

    def active_alerts(self, device_id: str | None) -> dict[str, Any]:
        with self._database.pool.connection() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS alert_count,
                       COUNT(*) FILTER (WHERE temperature_alert) AS temperature_alert_count,
                       COUNT(*) FILTER (WHERE humidity_alert) AS humidity_alert_count,
                       COUNT(*) FILTER (WHERE quality_alert) AS quality_alert_count
                FROM vw_alerts
                WHERE measured_at >= now() - INTERVAL '1 hour'
                  AND (%(device)s::text IS NULL OR device_id = %(device)s)
                """,
                {"device": device_id},
            ).fetchone()
        return dict(row)

    def connection_status(self, device_id: str | None) -> list[dict[str, Any]]:
        with self._database.pool.connection() as connection:
            rows = connection.execute(
                """
                SELECT device_id, group_id, device_name, last_seen_at, online
                FROM vw_device_status
                WHERE (%(device)s::text IS NULL OR device_id = %(device)s)
                ORDER BY online DESC, last_seen_at DESC NULLS LAST
                """,
                {"device": device_id},
            ).fetchall()
        return [dict(row) for row in rows]
