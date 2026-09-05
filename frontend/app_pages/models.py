"""Comparación temporal comprobable de modelos para humedad del suelo."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from api_client import ApiError
from prediction import (
    PredictionConfig,
    PredictionValidationError,
    compare_models,
    samples_to_frame,
)
from services import get_api_client


@st.cache_data(ttl=30, show_spinner="Preparando modelos...")
def load_model_data(api_base_url: str, limit: int, device_id: str | None) -> pd.DataFrame:
    """Obtiene telemetría y conserva secuencia, periodo y banderas de calidad."""
    samples = get_api_client(api_base_url).list_telemetry(
        limit=limit,
        device_id=device_id,
    )
    return samples_to_frame(samples)


def _combined_export(
    predictions: pd.DataFrame,
    metrics: pd.DataFrame,
) -> bytes:
    """Incluye predicciones y métricas en un único CSV autoidentificable."""
    prediction_rows = predictions.copy()
    prediction_rows.insert(0, "tipo_registro", "prediccion")
    metric_rows = metrics.copy()
    metric_rows.insert(0, "tipo_registro", "metrica")
    combined = pd.concat([prediction_rows, metric_rows], ignore_index=True, sort=False)
    return combined.to_csv(index=False).encode("utf-8-sig")


try:
    devices = get_api_client(st.session_state.api_base_url).list_devices()
except ApiError as exc:
    st.error(str(exc))
    st.stop()

device = st.selectbox("Dispositivo", ["Todos", *devices])
limit = st.slider("Muestras para modelar", 50, 5000, 1000, step=50)
k_neighbors = st.slider("Vecinos de k-NN", 1, 10, 5)
max_gap_factor = st.select_slider(
    "Tolerancia máxima del intervalo",
    options=[1.0, 1.25, 1.5, 2.0, 3.0],
    value=1.5,
    help="Un par se descarta si tarda más que este factor por el periodo reportado.",
)

try:
    frame = load_model_data(
        st.session_state.api_base_url,
        limit,
        None if device == "Todos" else device,
    )
    config = PredictionConfig(
        k_neighbors=k_neighbors,
        max_gap_factor=max_gap_factor,
    )
    result = compare_models(frame, config)
except (ApiError, PredictionValidationError) as exc:
    st.info(f"No fue posible comparar los modelos: {exc}")
    st.stop()

st.subheader("Comparación temporal 80/20 sin fuga")
comparison = result.metrics.rename(
    columns={
        "algorithm": "Algoritmo",
        "mae": "MAE",
        "rmse": "RMSE",
        "r2": "R²",
        "bias": "Sesgo",
    }
)
st.dataframe(
    comparison,
    width="stretch",
    hide_index=True,
    column_config={
        "MAE": st.column_config.NumberColumn(format="%.4f"),
        "RMSE": st.column_config.NumberColumn(format="%.4f"),
        "R²": st.column_config.NumberColumn(format="%.4f"),
        "Sesgo": st.column_config.NumberColumn(format="%.4f"),
    },
)
best = comparison.sort_values("RMSE").iloc[0]
st.success(f"Menor RMSE: {best['Algoritmo']} ({best['RMSE']:.3f}).")

linear_diagnostics = result.diagnostics["linear"]
st.caption(
    f"Pares válidos: {result.diagnostics['pair_count']} · "
    f"Entrenamiento: {result.diagnostics['train_size']} · "
    f"Prueba: {result.diagnostics['test_size']} · "
    f"Filas purgadas en la frontera: {result.diagnostics['purged_rows']} · "
    f"Rango lineal: {linear_diagnostics['rank']}/{linear_diagnostics['columns']} · "
    f"Predicciones recortadas: {linear_diagnostics['clipped_predictions']}"
)
if not linear_diagnostics["well_conditioned"]:
    st.warning(
        "La matriz de regresión tiene variables redundantes o condición numérica alta. "
        "La predicción se calculó con mínimos cuadrados, pero debe interpretarse con cautela."
    )

chart = result.predictions.rename(
    columns={
        "actual": "Real",
        "persistence": "Persistencia",
        "linear_regression": "Regresión lineal",
        "knn": "k-NN",
    }
)
st.line_chart(
    chart.set_index("target_time")[["Real", "Persistencia", "Regresión lineal", "k-NN"]],
    y_label="Humedad del suelo (%)",
)
st.dataframe(
    chart[
        [
            "target_time",
            "device",
            "target_sequence",
            "Real",
            "Persistencia",
            "Regresión lineal",
            "k-NN",
        ]
    ],
    width="stretch",
    hide_index=True,
)
st.download_button(
    "Descargar predicciones y métricas (.csv)",
    _combined_export(result.predictions, result.metrics),
    file_name=f"predicciones_metricas_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.csv",
    mime="text/csv; charset=utf-8",
    icon=":material/download:",
)
st.caption(
    "Demostración académica: solo se forman pares sequence+1 del mismo ESP32, se "
    "controla el intervalo reportado y el objetivo más reciente del entrenamiento queda "
    "antes del inicio de prueba. La persistencia permite comprobar si los modelos aportan "
    "valor. Se requieren calibración física y más datos antes de automatizar riego real."
)
