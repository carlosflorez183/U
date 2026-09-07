"""Pool y comprobaciones de PostgreSQL portable."""

from __future__ import annotations

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

_REQUIRED_TABLES = {
    "iot_groups",
    "devices",
    "sensor_types",
    "sensors",
    "calibrations",
    "telemetry_samples",
    "sensor_measurements",
    "quality_flag_types",
    "sample_quality_flags",
    "device_credentials",
}


class PostgresDatabase:
    """Gestiona conexiones y verifica el esquema académico al arrancar."""

    def __init__(self, database_url: str, *, min_size: int = 1, max_size: int = 10) -> None:
        self.pool = ConnectionPool(
            conninfo=database_url,
            min_size=min_size,
            max_size=max_size,
            open=False,
            kwargs={"row_factory": dict_row},
        )

    def open(self) -> None:
        self.pool.open(wait=True, timeout=30)

    def close(self) -> None:
        self.pool.close()

    def ping(self) -> None:
        with self.pool.connection() as connection:
            connection.execute("SELECT 1").fetchone()

    def verify_schema(self) -> None:
        """Falla rápido si faltan las tablas o la migración de seguridad."""
        with self.pool.connection() as connection:
            table_rows = connection.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                """
            ).fetchall()
            present = {str(row["table_name"]) for row in table_rows}
            missing = sorted(_REQUIRED_TABLES - present)
            if missing:
                raise RuntimeError(
                    "Esquema PostgreSQL incompleto; faltan: " + ", ".join(missing)
                )
            portability_migration = connection.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM schema_migrations
                    WHERE version = '003_postgresql_portability'
                ) AS applied
                """
            ).fetchone()
            if not portability_migration["applied"]:
                raise RuntimeError(
                    "Debe aplicarse la migración 003_postgresql_portability."
                )
