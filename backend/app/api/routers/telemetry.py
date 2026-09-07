"""API v2 de ingesta, consulta, exportación y eventos IoT."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, WebSocket, WebSocketDisconnect, status
from psycopg import Error as PostgresError
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import (
    get_record_event_hub,
    get_telemetry_service,
    require_ingest_principal,
)
from app.api.realtime import RecordEventHub
from app.api.telemetry_schemas import (
    IDENTIFIER_PATTERN,
    TelemetryIngestRequest,
    TelemetrySampleResponse,
)
from app.application.commands import IngestTelemetryCommand, TelemetryQuery
from app.application.exports import ExportFormat
from app.application.telemetry_service import TelemetryService
from app.domain.auth import IngestPrincipal

router = APIRouter(prefix="/api/v2/telemetry", tags=["Telemetría IoT"])
TelemetryVariable = Literal["soil_percent", "rain_percent", "soil_adc", "rain_adc"]


@router.post("/samples", response_model=TelemetrySampleResponse, status_code=status.HTTP_201_CREATED)
async def ingest_sample(
    payload: TelemetryIngestRequest,
    response: Response,
    principal: Annotated[IngestPrincipal, Depends(require_ingest_principal)],
    service: Annotated[TelemetryService, Depends(get_telemetry_service)],
    event_hub: Annotated[RecordEventHub, Depends(get_record_event_hub)],
) -> TelemetrySampleResponse:
    """Recibe una muestra; el backend asigna sequence e identifica reintentos exactos."""
    command = IngestTelemetryCommand(
        schema_version=payload.schema_version,
        group_id=payload.group_id,
        device_id=payload.device_id,
        measured_at=payload.measured_at,
        sampling_period_seconds=payload.sampling_period_seconds,
        soil_raw_adc=payload.soil_moisture.raw_adc,
        soil_percent=payload.soil_moisture.percent,
        rain_raw_adc=payload.rain.raw_adc,
        rain_wetness_percent=payload.rain.wetness_percent,
        rain_detected=payload.rain.detected,
        principal=principal,
    )
    try:
        sample, created = await run_in_threadpool(service.ingest, command)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except PostgresError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo almacenar la muestra en PostgreSQL.",
        ) from exc

    result = TelemetrySampleResponse.from_domain(sample, duplicate=not created)
    if not created:
        response.status_code = status.HTTP_200_OK
    else:
        await event_hub.publish(
            {"type": "telemetry.sample.created", "sample": result.model_dump(mode="json")}
        )
    return result


def _query(
    *,
    limit: int,
    device_id: str | None,
    group_id: str | None,
    from_at: datetime | None,
    to_at: datetime | None,
    variable: str | None,
    min_value: float | None,
    max_value: float | None,
) -> TelemetryQuery:
    return TelemetryQuery(
        limit=limit,
        device_id=device_id,
        group_id=group_id,
        from_at=from_at,
        to_at=to_at,
        variable=variable,
        min_value=min_value,
        max_value=max_value,
    )


@router.get("/samples", response_model=list[TelemetrySampleResponse])
def list_samples(
    service: Annotated[TelemetryService, Depends(get_telemetry_service)],
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
    device_id: Annotated[
        str | None,
        Query(min_length=2, max_length=64, pattern=IDENTIFIER_PATTERN),
    ] = None,
    group_id: Annotated[
        str | None,
        Query(min_length=2, max_length=64, pattern=IDENTIFIER_PATTERN),
    ] = None,
    from_at: Annotated[datetime | None, Query(alias="from")] = None,
    to_at: Annotated[datetime | None, Query(alias="to")] = None,
    variable: TelemetryVariable | None = None,
    min_value: Annotated[float | None, Query(allow_inf_nan=False)] = None,
    max_value: Annotated[float | None, Query(allow_inf_nan=False)] = None,
) -> list[TelemetrySampleResponse]:
    """Consulta por dispositivo, grupo, fecha, variable y rango de valores."""
    try:
        samples = service.list_samples(
            _query(
                limit=limit,
                device_id=device_id,
                group_id=group_id,
                from_at=from_at,
                to_at=to_at,
                variable=variable,
                min_value=min_value,
                max_value=max_value,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except PostgresError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Error consultando PostgreSQL.") from exc
    return [TelemetrySampleResponse.from_domain(sample) for sample in samples]


@router.get("/devices", response_model=list[str])
def list_devices(
    service: Annotated[TelemetryService, Depends(get_telemetry_service)],
) -> list[str]:
    try:
        return service.list_device_ids()
    except PostgresError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Error consultando dispositivos.") from exc


@router.get("/groups", response_model=list[str])
def list_groups(
    service: Annotated[TelemetryService, Depends(get_telemetry_service)],
) -> list[str]:
    try:
        return service.list_group_ids()
    except PostgresError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Error consultando grupos.") from exc


@router.get("/export/{export_format}", response_class=Response)
async def export_samples(
    export_format: ExportFormat,
    service: Annotated[TelemetryService, Depends(get_telemetry_service)],
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
    device_id: Annotated[
        str | None,
        Query(min_length=2, max_length=64, pattern=IDENTIFIER_PATTERN),
    ] = None,
    group_id: Annotated[
        str | None,
        Query(min_length=2, max_length=64, pattern=IDENTIFIER_PATTERN),
    ] = None,
    from_at: Annotated[datetime | None, Query(alias="from")] = None,
    to_at: Annotated[datetime | None, Query(alias="to")] = None,
    variable: TelemetryVariable | None = None,
    min_value: Annotated[float | None, Query(allow_inf_nan=False)] = None,
    max_value: Annotated[float | None, Query(allow_inf_nan=False)] = None,
) -> Response:
    try:
        query = _query(
            limit=limit,
            device_id=device_id,
            group_id=group_id,
            from_at=from_at,
            to_at=to_at,
            variable=variable,
            min_value=min_value,
            max_value=max_value,
        )
        exported = await run_in_threadpool(service.export_samples, query, export_format)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except PostgresError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Error exportando desde PostgreSQL.") from exc
    return Response(
        content=exported.content,
        media_type=exported.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{exported.filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.websocket("/events")
async def telemetry_events(websocket: WebSocket) -> None:
    """Publica nuevas muestras después de confirmar la transacción SQL."""
    event_hub: RecordEventHub = websocket.app.state.record_event_hub
    await event_hub.connect(websocket)
    try:
        while True:
            await websocket.receive()
    except (RuntimeError, WebSocketDisconnect):
        pass
    finally:
        await event_hub.disconnect(websocket)
