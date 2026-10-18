"""Genera el dataset DHT22 (2 dias, lectura cada 20 s) para KNIME y Flowise.

Salida: datasets/dataset_dht22.csv (~8.700 filas) con columnas:
measured_at, group_id, device_id, temperature_celsius, humidity_percent,
temp_status, humidity_status.

Incluye imperfectos a proposito para la limpieza de KNIME:
- ~40 filas con humedad vacia (nulos)
- ~15 filas duplicadas exactas
- ~25 valores atipicos (picos de temperatura o humedad)
- 5 filas con decimal con coma ("25,3") para practicar conversion de tipos

Uso: python scripts/generar_dataset_dht22.py
"""

from __future__ import annotations

import csv
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEED = 20261018
STEP_SECONDS = 20
DAYS = 2
START = datetime(2026, 10, 16, 0, 0, 0, tzinfo=timezone.utc)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT_ROOT / "datasets" / "dataset_dht22.csv"


def temp_status(value: float) -> str:
    if value < 18:
        return "COLD"
    if value > 28:
        return "HOT"
    return "COMFORT"


def humidity_status(value: float) -> str:
    if value < 30:
        return "DRY"
    if value >= 70:
        return "HUMID"
    return "COMFORT"


def main() -> None:
    random.seed(SEED)
    rows: list[list[object]] = []
    total = DAYS * 24 * 60 * 60 // STEP_SECONDS
    for index in range(total):
        moment = START + timedelta(seconds=index * STEP_SECONDS)
        hour = moment.hour + moment.minute / 60.0
        # Patron diurno: maximo ~14:00, minimo ~05:00, humedad antifasica.
        temperature = (
            23.0
            + 5.5 * math.sin(2 * math.pi * (hour - 10.5) / 24.0)
            + random.gauss(0, 0.6)
        )
        humidity = (
            62.0
            - 9.0 * math.sin(2 * math.pi * (hour - 10.5) / 24.0)
            + random.gauss(0, 2.0)
        )
        temperature = round(min(max(temperature, 12.0), 36.0), 1)
        humidity = round(min(max(humidity, 18.0), 96.0), 1)
        rows.append(
            [
                moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "grupo-01",
                "esp32-grupo-01",
                f"{temperature:.1f}",
                f"{humidity:.1f}",
                temp_status(temperature),
                humidity_status(humidity),
            ]
        )

    # Imperfectos: atipicos (picos) en posiciones fijas para que sean verificables.
    for index in range(0, total, max(total // 25, 1)):
        row = rows[index]
        if index % 2 == 0:
            spike = round(float(row[3]) + random.choice([13.5, 15.0, -11.0]), 1)
            row[3] = f"{spike:.1f}"
            row[5] = temp_status(spike)
        else:
            spike = round(min(max(float(row[4]) + random.choice([30.0, 33.0, -35.0]), 2.0), 99.0), 1)
            row[4] = f"{spike:.1f}"
            row[6] = humidity_status(spike)

    # Nulos: humedad vacia.
    for index in range(37, total, max(total // 40, 1)):
        rows[index][4] = ""
        rows[index][6] = ""

    # Decimal con coma (problema tipico de exportaciones Excel).
    for index in range(111, total, max(total // 5, 1)):
        rows[index][3] = str(rows[index][3]).replace(".", ",", 1)

    # Duplicados exactos.
    duplicates = [list(rows[i]) for i in range(500, 500 + 15)]
    rows.extend(duplicates)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "measured_at",
                "group_id",
                "device_id",
                "temperature_celsius",
                "humidity_percent",
                "temp_status",
                "humidity_status",
            ]
        )
        writer.writerows(rows)

    valid_temps = [float(r[3].replace(",", ".")) for r in rows if r[3]]
    valid_hums = [float(r[4]) for r in rows if r[4]]
    print(f"Archivo: {OUTPUT}")
    print(f"Filas: {len(rows)}")
    print(f"Temperatura promedio: {sum(valid_temps) / len(valid_temps):.2f} C")
    print(f"Temperatura maxima: {max(valid_temps):.1f} C")
    print(f"Temperatura minima: {min(valid_temps):.1f} C")
    print(f"Humedad promedio: {sum(valid_hums) / len(valid_hums):.2f} %")
    print(f"Humedad maxima: {max(valid_hums):.1f} %")
    print(f"Humedad minima: {min(valid_hums):.1f} %")
    nulos = sum(1 for r in rows if not r[4])
    print(f"Filas con humedad vacia: {nulos}")
    print(f"Duplicados agregados: {len(duplicates)}")


if __name__ == "__main__":
    main()
