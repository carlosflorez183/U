"""Cliente WebSocket por sesión para eventos de telemetría."""

from __future__ import annotations

import json
import threading
from queue import Empty, Full, Queue
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import websocket


class EventListener:
    """Escucha eventos en un hilo y los entrega al script de Streamlit."""

    def __init__(
        self,
        api_base_url: str,
        *,
        websocket_path: str = "/api/v2/telemetry/events",
        event_types: set[str] | None = None,
    ) -> None:
        self.api_base_url = api_base_url.rstrip("/")
        self.websocket_path = websocket_path
        self.event_types = event_types or {"telemetry.sample.created"}
        self.websocket_url = self._to_websocket_url(self.api_base_url, websocket_path)
        self._events: Queue[dict[str, Any]] = Queue(maxsize=200)
        self._stop_event = threading.Event()
        self._connected_event = threading.Event()
        self._socket_lock = threading.Lock()
        self._socket: websocket.WebSocket | None = None
        self._thread: threading.Thread | None = None

    @property
    def is_connected(self) -> bool:
        return self._connected_event.is_set()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._listen, daemon=True, name="telemetry-events"
        )
        self._thread.start()

    def close(self) -> None:
        self._stop_event.set()
        with self._socket_lock:
            if self._socket is not None:
                self._socket.close()

    def drain(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        while True:
            try:
                events.append(self._events.get_nowait())
            except Empty:
                return events

    def _listen(self) -> None:
        retry_delay = 1.0
        while not self._stop_event.is_set():
            try:
                connection = websocket.create_connection(self.websocket_url, timeout=5)
                connection.settimeout(1)
                with self._socket_lock:
                    self._socket = connection
                self._connected_event.set()
                retry_delay = 1.0
                while not self._stop_event.is_set():
                    try:
                        message = connection.recv()
                    except websocket.WebSocketTimeoutException:
                        continue
                    if not message:
                        raise websocket.WebSocketConnectionClosedException("Canal cerrado.")
                    self._queue_event(message)
            except (OSError, websocket.WebSocketException):
                self._connected_event.clear()
                self._stop_event.wait(retry_delay)
                retry_delay = min(retry_delay * 2, 10.0)
            finally:
                self._connected_event.clear()
                with self._socket_lock:
                    if self._socket is not None:
                        self._socket.close()
                    self._socket = None

    def _queue_event(self, message: str) -> None:
        try:
            event = json.loads(message)
        except json.JSONDecodeError:
            return
        if not isinstance(event, dict) or event.get("type") not in self.event_types:
            return
        try:
            self._events.put_nowait(event)
        except Full:
            try:
                self._events.get_nowait()
            except Empty:
                pass
            self._events.put_nowait(event)

    @staticmethod
    def _to_websocket_url(api_base_url: str, path: str) -> str:
        parsed = urlsplit(api_base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("La URL de API debe comenzar por http:// o https://.")
        scheme = "wss" if parsed.scheme == "https" else "ws"
        return urlunsplit((scheme, parsed.netloc, path, "", ""))


# Alias para clientes antiguos que todavía importen el nombre previo.
RecordEventListener = EventListener
