"""Canal de eventos WebSocket para actualizaciones de registros."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket


class RecordEventHub:
    """Difunde eventos de registros a los clientes conectados a esta instancia."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        """Acepta y registra una conexión WebSocket."""
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        """Elimina una conexión que se cerró o dejó de responder."""
        async with self._lock:
            self._connections.discard(websocket)

    async def publish(self, event: dict[str, Any]) -> None:
        """Publica un evento sin afectar la operación si un cliente falla."""
        async with self._lock:
            connections = tuple(self._connections)

        failed_connections: list[WebSocket] = []
        for websocket in connections:
            try:
                await websocket.send_json(event)
            except Exception:
                failed_connections.append(websocket)

        for websocket in failed_connections:
            await self.disconnect(websocket)

    async def close_all(self) -> None:
        """Cierra las conexiones activas al apagar la aplicación."""
        async with self._lock:
            connections = tuple(self._connections)
            self._connections.clear()

        for websocket in connections:
            try:
                await websocket.close()
            except Exception:
                pass
