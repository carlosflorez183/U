"""Simulador autenticado de una muestra enviada por el circuito ESP32."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

import streamlit as st

from api_client import ApiError
from services import get_api_client

_MAX_ATTEMPTS = 50
_STATUS_LABELS = {
    "success": "✅ Guardada",
    "duplicate": "⚠️ Duplicada",
    "failure": "❌ Falló",
}

st.session_state.setdefault("telemetry_attempts", [])

st.write(
    "Simula el JSON que enviará el ESP32. El dispositivo debe estar registrado "
    "y la credencial debe estar vinculada desde la página Administración."
)
st.warning(
    "La API key y secret key se envían como headers y nunca forman parte del JSON. "
    "No use credenciales reales en capturas o sustentaciones públicas."
)

st.info(
    "El backend asigna automáticamente `sequence`. El dispositivo y este simulador no la envían."
)

with st.form("telemetry_form"):
    credentials = st.container(horizontal=True)
    api_key = credentials.text_input("API key", type="password")
    secret_key = credentials.text_input("Secret key", type="password")

    identity = st.container(horizontal=True)
    group_id = identity.text_input("Grupo", value="grupo-01")
    device_id = identity.text_input("Dispositivo", value="esp32-grupo-01")
    sampling_period = identity.selectbox("Periodo (s)", options=[5, 10])

    st.subheader("Sensor DHT22 ambiental")
    ambient = st.container(horizontal=True)
    temperature = ambient.number_input(
        "Temperatura (°C)", min_value=-40.0, max_value=80.0, value=23.4, step=0.1
    )
    humidity = ambient.number_input(
        "Humedad relativa (%)", min_value=0.0, max_value=100.0, value=65.2, step=0.1
    )

    submitted = st.form_submit_button(
        "Enviar muestra", icon=":material/sensors:", type="primary"
    )

if submitted:
    attempted_at = datetime.now(timezone.utc).isoformat()
    local_request_id = str(uuid4())
    payload = {
        "schema_version": "2.0",
        "group_id": group_id,
        "device_id": device_id,
        "measured_at": attempted_at,
        "sampling_period_seconds": sampling_period,
        "ambient": {
            "temperature_celsius": temperature,
            "humidity_percent": humidity,
        },
    }
    attempt = {
        "status": "failure",
        "sent": False,
        "attempted_at": attempted_at,
        "device_id": device_id,
        "sequence": None,
        "payload": deepcopy(payload),
        "http_status": None,
        "error_code": None,
        "error_message": None,
        "error_details": [],
        "request_id": local_request_id,
        "response": None,
    }

    if not api_key or not secret_key:
        attempt["error_code"] = "MISSING_CREDENTIALS"
        attempt["error_message"] = "API key y secret key son obligatorias."
        st.error(attempt["error_message"])
    else:
        attempt["sent"] = True
        try:
            api_response = get_api_client(
                st.session_state.api_base_url
            ).ingest_telemetry_with_metadata(
                payload,
                api_key=api_key,
                secret_key=secret_key,
                request_id=local_request_id,
            )
        except ApiError as exc:
            attempt["http_status"] = exc.status_code
            attempt["error_code"] = exc.code
            attempt["error_message"] = exc.message
            attempt["error_details"] = deepcopy(exc.details)
            attempt["request_id"] = exc.request_id or local_request_id
            st.error(str(exc))
        else:
            saved = api_response.data
            duplicate = bool(saved.get("duplicate"))
            attempt["status"] = "duplicate" if duplicate else "success"
            attempt["http_status"] = api_response.status_code
            attempt["request_id"] = api_response.request_id or local_request_id
            attempt["sequence"] = saved["sequence"]
            attempt["response"] = deepcopy(saved)
            st.cache_data.clear()
            if duplicate:
                st.warning("La API reconoció un reintento idéntico y devolvió la muestra original.")
            else:
                st.success(
                    f"Muestra guardada con id `{saved['id']}` por "
                    f"`{saved.get('inserted_by_alias', 'credencial sin alias')}`."
                )
            st.json(saved)

    attempts = st.session_state["telemetry_attempts"]
    attempts.insert(0, attempt)
    del attempts[_MAX_ATTEMPTS:]

st.divider()
st.subheader("Trazabilidad de envíos")
attempts = st.session_state["telemetry_attempts"]
if not attempts:
    st.info("Aún no hay intentos registrados en esta sesión.")
else:
    summary = [
        {
            "Estado": _STATUS_LABELS[item["status"]],
            "Fecha UTC": item["attempted_at"],
            "Dispositivo": item["device_id"],
            "Secuencia backend": item["sequence"] if item["sequence"] is not None else "N/D",
            "HTTP": item["http_status"] if item["http_status"] is not None else "N/D",
            "Código": item["error_code"] or "—",
            "Request ID": item["request_id"],
        }
        for item in attempts
    ]
    st.dataframe(summary, width="stretch", hide_index=True)

    if st.button("Limpiar historial", icon=":material/delete_sweep:"):
        st.session_state["telemetry_attempts"] = []
        st.rerun()

    for index, item in enumerate(attempts):
        http_status = item["http_status"] if item["http_status"] is not None else "N/D"
        assigned_sequence = item["sequence"] if item["sequence"] is not None else "N/D"
        label = (
            f"{_STATUS_LABELS[item['status']]} · {item['device_id']} · "
            f"secuencia backend {assigned_sequence} · HTTP {http_status}"
        )
        with st.expander(label, expanded=index == 0):
            st.caption(f"Fecha UTC: {item['attempted_at']}")
            st.write(f"**Request ID:** `{item['request_id']}`")
            st.write(f"**Solicitud HTTP enviada:** {'sí' if item['sent'] else 'no'}")
            if item["error_code"]:
                st.error(f"{item['error_code']}: {item['error_message']}")
                st.write("**Detalles del error:**")
                st.json(item["error_details"])
            st.write("**JSON enviado:**")
            st.json(item["payload"])
            if item["response"] is not None:
                st.write("**Respuesta de la API:**")
                st.json(item["response"])

with st.expander("Contrato HTTP para el ESP32"):
    st.code(
        '''X-API-Key: ak_...
X-Secret-Key: sk_...
Content-Type: application/json''',
        language="http",
    )
    st.code(
        '''{
  "schema_version": "2.0",
  "group_id": "grupo-01",
  "device_id": "esp32-grupo-01",
  "measured_at": "2026-09-07T22:30:00Z",
  "sampling_period_seconds": 5,
  "ambient": {"temperature_celsius": 23.4, "humidity_percent": 65.2}
}''',
        language="json",
    )
