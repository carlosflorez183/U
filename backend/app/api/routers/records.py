"""API v1 compatible para registros JSONB."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, WebSocket, WebSocketDisconnect, status
from psycopg import Error as PostgresError
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import get_record_event_hub, get_record_service
from app.api.realtime import RecordEventHub
from app.api.schemas import RecordCreateRequest, RecordResponse
from app.application.commands import CreateRecordCommand
from app.application.exports import ExportFormat
from app.application.services import RecordService
from app.domain.entities import Record

router = APIRouter(prefix="/api/v1/records", tags=["Registros"])


def to_response(record: Record) -> RecordResponse:
    return RecordResponse(
        id=record.id,
        data=dict(record.data),
        source=record.source,
        created_at=record.created_at,
    )


@router.post("", response_model=RecordResponse, status_code=status.HTTP_201_CREATED)
async def create_record(
    payload: RecordCreateRequest,
    service: Annotated[RecordService, Depends(get_record_service)],
    event_hub: Annotated[RecordEventHub, Depends(get_record_event_hub)],
) -> RecordResponse:
    """Recibe JSON, lo guarda en PostgreSQL JSONB y publica `record.created`."""
    try:
        record = await run_in_threadpool(
            service.create_record,
            CreateRecordCommand(data=payload.data, source=payload.source),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except PostgresError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="PostgreSQL no está disponible.") from exc

    response = to_response(record)
    await event_hub.publish(
        {"type": "record.created", "record": response.model_dump(mode="json")}
    )
    return response


@router.get("", response_model=list[RecordResponse])
def list_records(
    service: Annotated[RecordService, Depends(get_record_service)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[RecordResponse]:
    try:
        return [to_response(record) for record in service.list_recent_records(limit)]
    except PostgresError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="PostgreSQL no está disponible.") from exc


@router.get("/export/{export_format}", response_class=Response)
async def export_records(
    export_format: ExportFormat,
    service: Annotated[RecordService, Depends(get_record_service)],
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> Response:
    try:
        exported_file = await run_in_threadpool(
            service.export_recent_records, export_format, limit
        )
    except PostgresError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="PostgreSQL no está disponible.") from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return Response(
        content=exported_file.content,
        media_type=exported_file.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{exported_file.filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.websocket("/events")
async def record_events(websocket: WebSocket) -> None:
    event_hub: RecordEventHub = websocket.app.state.record_event_hub
    await event_hub.connect(websocket)
    try:
        while True:
            await websocket.receive()
    except (RuntimeError, WebSocketDisconnect):
        pass
    finally:
        await event_hub.disconnect(websocket)
