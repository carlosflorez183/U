"""API de analítica en tiempo real para el menú del teclado matricial."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg import Error as PostgresError
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import get_menu_service
from app.api.menu_schemas import (
    AlertReport,
    DailyExtremes,
    DeviceConnectionStatus,
    HourlyAverage,
    OutlierReport,
    RealtimeReading,
    TrendReport,
)
from app.api.telemetry_schemas import IDENTIFIER_PATTERN
from app.application.menu_service import MenuService

router = APIRouter(prefix="/api/v2/menu", tags=["Menú teclado matricial"])

DeviceParam = Annotated[
    str | None,
    Query(min_length=2, max_length=64, pattern=IDENTIFIER_PATTERN),
]


def _run(service_call, *args):
    try:
        return run_in_threadpool(service_call, *args)
    except PostgresError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Error consultando PostgreSQL.",
        ) from exc


@router.get("/realtime", response_model=RealtimeReading)
async def realtime(
    service: Annotated[MenuService, Depends(get_menu_service)],
    device_id: DeviceParam = None,
) -> RealtimeReading:
    """Opción 1 del menú: valor actual de cada sensor."""
    row = await _run(service.realtime, device_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay lecturas registradas todavía.",
        )
    return RealtimeReading(**row)


@router.get("/hourly-average", response_model=HourlyAverage)
async def hourly_average(
    service: Annotated[MenuService, Depends(get_menu_service)],
    device_id: DeviceParam = None,
) -> HourlyAverage:
    """Opción 2 del menú: promedio de la última hora."""
    return HourlyAverage(**await _run(service.hourly_average, device_id))


@router.get("/daily-extremes", response_model=DailyExtremes)
async def daily_extremes(
    service: Annotated[MenuService, Depends(get_menu_service)],
    device_id: DeviceParam = None,
) -> DailyExtremes:
    """Opción 3 del menú: máximo y mínimo del día."""
    return DailyExtremes(**await _run(service.daily_extremes, device_id))


@router.get("/trend", response_model=TrendReport)
async def trend(
    service: Annotated[MenuService, Depends(get_menu_service)],
    device_id: DeviceParam = None,
) -> TrendReport:
    """Opción 4 del menú: desviación estándar y tendencia horaria."""
    return TrendReport(**await _run(service.trend, device_id))


@router.get("/outliers", response_model=OutlierReport)
async def outliers(
    service: Annotated[MenuService, Depends(get_menu_service)],
    device_id: DeviceParam = None,
) -> OutlierReport:
    """Opción 5 del menú: valores atípicos del día (2σ del promedio)."""
    return OutlierReport(**await _run(service.outliers_today, device_id))


@router.get("/alerts", response_model=AlertReport)
async def alerts(
    service: Annotated[MenuService, Depends(get_menu_service)],
    device_id: DeviceParam = None,
) -> AlertReport:
    """Opción 6 del menú: conteo de alertas activas en la última hora."""
    return AlertReport(**await _run(service.active_alerts, device_id))


@router.get("/connection", response_model=list[DeviceConnectionStatus])
async def connection(
    service: Annotated[MenuService, Depends(get_menu_service)],
    device_id: DeviceParam = None,
) -> list[DeviceConnectionStatus]:
    """Opción 7 del menú: estado de conexión a la nube."""
    rows = await _run(service.connection_status, device_id)
    return [DeviceConnectionStatus(**row) for row in rows]
