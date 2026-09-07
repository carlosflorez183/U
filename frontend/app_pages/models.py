"""Modelo demostrativo de lluvia con una interfaz mínima."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

import pandas as pd
import streamlit as st

from api_client import ApiError
from prediction import (
    PredictionValidationError,
    estimate_rain_from_soil,
    samples_to_frame,
)
from services import get_api_client
from ui import render_section_intro


_DEMO_DEVICE_ID = "model-rain-demo-01"
_FIXED_THRESHOLD = 0.50
_MAX_RECORDS = 5000


def _period_bounds(period: str) -> tuple[datetime, datetime]:
    """Devuelve el rango UTC de hoy o de la última semana."""
    now = datetime.now(timezone.utc)
    if period == "Hoy":
        start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
    else:
        start = now - timedelta(days=7)
    return start, now


def _built_in_demo_frame(start: datetime, end: datetime) -> pd.DataFrame:
    """Crea una referencia demo separada cuando aún no existe en PostgreSQL."""
    duration_seconds = max(0.0, (end - start).total_seconds())
    count = min(_MAX_RECORDS, max(120, int(duration_seconds // 300) + 1))
    if count == 1:
        timestamps = [end]
    else:
        step = duration_seconds / (count - 1)
        timestamps = [start + timedelta(seconds=step * index) for index in range(count)]

    samples: list[dict[str, object]] = []
    for sequence, measured_at in enumerate(timestamps):
        soil_percent = 15.0 + (sequence % 30) * 2.5
        rain_detected = 37.5 <= soil_percent <= 57.5 and sequence % 5 != 0
        samples.append(
            {
                "id": f"model-demo-{sequence}",
                "device_id": _DEMO_DEVICE_ID,
                "sequence": sequence,
                "measured_at": measured_at.isoformat(),
                "sampling_period_seconds": 5,
                "soil_moisture": {"percent": soil_percent},
                "rain": {
                    "wetness_percent": 68.0 if rain_detected else 3.0,
                    "detected": rain_detected,
                },
                "quality_flags": [],
            }
        )
    return samples_to_frame(samples)


@st.cache_data(ttl=30, show_spinner="Preparando el modelo demostrativo...")
def load_demo_data(
    api_base_url: str,
    from_at: str,
    to_at: str,
) -> tuple[pd.DataFrame, str]:
    """Usa model-rain-demo-01 de PostgreSQL o una referencia integrada aislada."""
    try:
        samples = get_api_client(api_base_url).list_telemetry(
            limit=_MAX_RECORDS,
            device_id=_DEMO_DEVICE_ID,
            from_at=from_at,
            to_at=to_at,
        )
        if len(samples) >= 5:
            frame = samples_to_frame(samples)
            confirmed = frame["detected"] & (frame["rain"] >= 10.0)
            if confirmed.any():
                return frame, "PostgreSQL · model-rain-demo-01"
    except (ApiError, PredictionValidationError):
        pass

    start = datetime.fromisoformat(from_at)
    end = datetime.fromisoformat(to_at)
    return _built_in_demo_frame(start, end), "Referencia demo integrada"


render_section_intro(
    "¿Lloverá según la humedad del suelo?",
    "Selecciona el periodo y escribe la humedad actual. El resto se calcula automáticamente.",
)

st.info(
    "Modelo demostrativo con umbral fijo de 50%. Usa el dispositivo aislado "
    "`model-rain-demo-01`; nunca mezcla la referencia demo con `esp32-grupo-01`."
)

with st.form("simple_rain_demo_form", border=True):
    period = st.radio(
        "Periodo histórico",
        options=["Hoy", "Esta semana"],
        horizontal=True,
    )
    soil_percent = st.number_input(
        "Humedad actual del suelo (%)",
        min_value=0.0,
        max_value=100.0,
        value=45.0,
        step=0.5,
    )
    submitted = st.form_submit_button(
        "Calcular",
        type="primary",
        width="stretch",
    )

if submitted:
    start, end = _period_bounds(period)
    st.session_state["simple_rain_demo_selection"] = {
        "period": period,
        "soil_percent": soil_percent,
        "from_at": start.isoformat(),
        "to_at": end.isoformat(),
    }

selection = st.session_state.get("simple_rain_demo_selection")
if selection is None:
    st.caption("El umbral, dispositivo y cantidad de registros son automáticos.")
    st.stop()

try:
    frame, data_source = load_demo_data(
        st.session_state.api_base_url,
        str(selection["from_at"]),
        str(selection["to_at"]),
    )
    estimate = estimate_rain_from_soil(
        frame,
        float(selection["soil_percent"]),
        threshold=_FIXED_THRESHOLD,
    )
except (ApiError, PredictionValidationError, KeyError) as exc:
    st.error(f"No fue posible calcular la estimación: {exc}")
    st.stop()

probability_percent = estimate.probability * 100.0
if estimate.predicted:
    st.warning("## Sí, es probable que llueva")
else:
    st.success("## No, es poco probable que llueva")
st.progress(
    estimate.probability,
    text=f"Probabilidad estimada: {probability_percent:.1f}%",
)

result_col_1, result_col_2, result_col_3 = st.columns(3)
result_col_1.metric("Humedad actual", f"{estimate.soil_percent:.1f}%")
result_col_2.metric("Probabilidad", f"{probability_percent:.1f}%")
result_col_3.metric("Umbral automático", "50%")

st.caption(
    f"Periodo: {selection['period']} · Fuente: {data_source} · "
    f"Registros analizados: {estimate.valid_rows} · "
    f"Casos similares: {len(estimate.neighbors)}."
)
if data_source == "Referencia demo integrada":
    st.warning(
        "Todavía no hay suficientes registros positivos de `model-rain-demo-01` en "
        "PostgreSQL. Para que la demostración funcione ahora, se utilizó una referencia "
        "sintética integrada que no modifica la base de datos."
    )

summary_tab, examples_tab = st.tabs(["Resultado", "Ejemplos utilizados"])
with summary_tab:
    rain_count = estimate.neighbor_rain_rows
    neighbor_count = len(estimate.neighbors)
    st.write(
        f"Para una humedad de **{estimate.soil_percent:.1f}%**, "
        f"**{rain_count} de {neighbor_count}** casos históricos similares indicaron "
        f"lluvia. Con el umbral fijo de **50%**, la respuesta es "
        f"**{'lluvia probable' if estimate.predicted else 'lluvia poco probable'}**."
    )
    st.markdown(
        "La lluvia se considera confirmada cuando `detected = true` y el sensor de "
        "lluvia registra al menos 10% de humedad."
    )

with examples_tab:
    rows = estimate.neighbors[
        ["fecha", "soil", "rain", "confirmed_rain", "soil_distance"]
    ].rename(
        columns={
            "fecha": "Fecha",
            "soil": "Suelo (%)",
            "rain": "Sensor lluvia (%)",
            "confirmed_rain": "Lluvia",
            "soil_distance": "Diferencia",
        }
    )
    st.dataframe(rows, hide_index=True, width="stretch")

st.warning(
    "Es una demostración de asociación entre sensores, no un pronóstico meteorológico. "
    "La humedad del suelo también puede deberse a lluvia anterior o riego."
)
