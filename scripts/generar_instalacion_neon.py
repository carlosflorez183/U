"""Genera docs/neon_instalacion.sql a partir de backend/migrations/001..005.

El SQL Editor de Neon (y el de la mayoria de proveedores cloud) no entiende
metacomandos de psql (\\gset, \\if, \\endif). La migracion 001 usa ese patron
para no recrear vistas existentes. Este generador lo reemplaza por SQL puro e
idempotente:

    DROP VIEW IF EXISTS <vista> CASCADE;
    CREATE VIEW <vista> AS ...;

Neon soporta la extension timescaledb (solo funciones Apache-2; sin
compresion, que este proyecto no usa).

Uso: python scripts/generar_instalacion_neon.py
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = PROJECT_ROOT / "backend" / "migrations"
OUTPUT_PATH = PROJECT_ROOT / "docs" / "neon_instalacion.sql"

MIGRATIONS = [
    "001_initial.sql",
    "002_device_credentials.sql",
    "003_postgresql_portability.sql",
    "004_ambient_dht22.sql",
    "005_timescale_menu.sql",
]

GSET_ALIAS = re.compile(r"AS\s+(?P<alias>[A-Za-z_][A-Za-z0-9_]*)\s+\\gset")


def _view_name(alias: str) -> str:
    return alias[len("create_"):] if alias.startswith("create_") else alias


def transform(text: str) -> str:
    """Quita metacomandos psql y convierte el bloque CASE...\\gset en un DROP."""
    lines = text.splitlines()
    output: list[str] = []
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if stripped.startswith("SELECT CASE"):
            block: list[str] = []
            while index < len(lines):
                block.append(lines[index])
                if "\\gset" in lines[index]:
                    break
                index += 1
            block_text = "\n".join(block)
            match = GSET_ALIAS.search(block_text)
            if match:
                view = _view_name(match.group("alias"))
                output.append(f"DROP VIEW IF EXISTS {view} CASCADE;")
            index += 1
            continue
        if stripped.startswith("\\"):
            index += 1
            continue
        output.append(lines[index])
        index += 1
    return "\n".join(output)


def main() -> None:
    parts = [
        "-- =====================================================================",
        "-- Instalacion completa en Neon (PostgreSQL + TimescaleDB) para el taller.",
        "-- Pasos: 1) abrir el SQL Editor de Neon; 2) pegar TODO este archivo;",
        "--        3) ejecutar una sola vez; 4) verificar con las consultas del",
        "--        final. Generado desde backend/migrations/001..005 con",
        "--        scripts/generar_instalacion_neon.py (sin metacomandos de psql).",
        "-- =====================================================================",
        "",
    ]
    for name in MIGRATIONS:
        source = (MIGRATIONS_DIR / name).read_text(encoding="utf-8")
        parts.append(f"-- ===== {name} =====")
        parts.append(transform(source).strip("\n"))
        parts.append("")
    OUTPUT_PATH.write_text("\n".join(parts).rstrip("\n") + "\n", encoding="utf-8")

    leftover = [
        (number, line)
        for number, line in enumerate(
            OUTPUT_PATH.read_text(encoding="utf-8").splitlines(), start=1
        )
        if line.lstrip().startswith("\\") or "\\gset" in line
    ]
    print(f"Generado: {OUTPUT_PATH}")
    print("Metacomandos psql restantes:", len(leftover))
    for number, line in leftover:
        print(f"  {number}: {line}")


if __name__ == "__main__":
    main()
