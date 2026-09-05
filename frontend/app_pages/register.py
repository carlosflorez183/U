"""Simulador autenticado de una muestra enviada por el circuito ESP32."""

from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from api_client import ApiError
from services import get_api_client

st.write(
    "Simula el JSON que enviará el ESP32. El dispositivo debe estar registrado "
    "y la credencial debe estar vinculada desde la página Administración."
)
st.warning(
    "La API key y secret key se envían como headers y nunca forman parte del JSON. "
    "No use credenciales reales en capturas o sustentaciones públicas."
)

with st.form("telemetry_form"):
    credentials = st.container(horizontal=True)
    api_key = credentials.text_input("API key", type="password")
    secret_key = credentials.text_input("Secret key", type="password")

    identity = st.container(horizontal=True)
    group_id = identity.text_input("Grupo", value="grupo-01")
    device_id = identity.text_input("Dispositivo", value="esp32-grupo-01")
    sequence = identity.number_input("Secuencia", min_value=0, value=1, step=1)
    sampling_period = identity.selectbox("Periodo (s)", options=[5, 10])

    st.subheader("Sensor capacitivo de humedad del suelo")
    soil = st.container(horizontal=True)
    soil_raw = soil.number_input("ADC suelo", min_value=0, max_value=4095, value=2400)
    soil_percent = soil.number_input(
        "Humedad del suelo (%)", min_value=0.0, max_value=100.0, value=45.0
    )

    st.subheader("Sensor de lluvia")
    rain = st.container(horizontal=True)
    rain_raw = rain.number_input("ADC lluvia", min_value=0, max_value=4095, value=3600)
    rain_percent = rain.number_input(
        "Superficie mojada (%)", min_value=0.0, max_value=100.0, value=5.0
    )
    rain_detected = rain.checkbox("Lluvia detectada", value=False)

    submitted = st.form_submit_button(
        "Enviar muestra", icon=":material/sensors:", type="primary"
    )

if submitted:
    if not api_key or not secret_key:
        st.error("API key y secret key son obligatorias.")
        st.stop()
    payload = {
        "schema_version": "2.0",
        "group_id": group_id,
        "device_id": device_id,
        "sequence": int(sequence),
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "sampling_period_seconds": sampling_period,
        "soil_moisture": {"raw_adc": soil_raw, "percent": soil_percent},
        "rain": {
            "raw_adc": rain_raw,
            "wetness_percent": rain_percent,
            "detected": rain_detected,
        },
    }
    try:
        saved = get_api_client(st.session_state.api_base_url).ingest_telemetry(
            payload,
            api_key=api_key,
            secret_key=secret_key,
        )
    except ApiError as exc:
        st.error(str(exc))
    else:
        st.cache_data.clear()
        if saved.get("duplicate"):
            st.warning("La secuencia ya existía; la API devolvió la muestra original.")
        else:
            st.success(
                f"Muestra guardada con id `{saved['id']}` por "
                f"`{saved.get('inserted_by_alias', 'credencial sin alias')}`."
            )
        st.json(saved)

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
  "sequence": 1,
  "measured_at": "2026-09-04T14:00:00Z",
  "sampling_period_seconds": 5,
  "soil_moisture": {"raw_adc": 2400, "percent": 45.0},
  "rain": {"raw_adc": 3600, "wetness_percent": 5.0, "detected": false}
}''',
        language="json",
    )
