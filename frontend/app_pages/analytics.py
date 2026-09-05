"""EDA, limpieza y anomalías sobre los datos filtrados."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pandas as pd
import streamlit as st

from api_client import ApiError
from services import get_api_client

_VARIABLES = {
    "Humedad del suelo (%)": ("soil_percent", "soil_percent", 0.0, 100.0, 0.5),
    "Humedad de lluvia (%)": ("rain_percent", "rain_percent", 0.0, 100.0, 0.5),
    "ADC del suelo": ("soil_adc", "soil_adc", 0, 4095, 1),
    "ADC de lluvia": ("rain_adc", "rain_adc", 0, 4095, 1),
}


@st.cache_data(ttl=30, show_spinner="Preparando análisis...")
def load_analysis_data(
    api_base_url: str,
    limit: int,
    device_id: str | None,
    group_id: str | None,
    from_at: str | None,
    to_at: str | None,
    variable: str,
    min_value: float,
    max_value: float,
) -> pd.DataFrame:
    samples = get_api_client(api_base_url).list_telemetry(
        limit=limit,
        device_id=device_id,
        group_id=group_id,
        from_at=from_at,
        to_at=to_at,
        variable=variable,
        min_value=min_value,
        max_value=max_value,
    )
    return pd.DataFrame(
        [
            {
                "id": item["id"],
                "fecha": pd.to_datetime(item["measured_at"], utc=True),
                "grupo": item["group_id"],
                "dispositivo": item["device_id"],
                "soil_percent": item["soil_moisture"]["percent"],
                "soil_adc": item["soil_moisture"]["raw_adc"],
                "rain_percent": item["rain"]["wetness_percent"],
                "rain_adc": item["rain"]["raw_adc"],
                "rain_detected": int(item["rain"]["detected"]),
                "quality_flags": ",".join(item["quality_flags"]),
            }
            for item in reversed(samples)
        ]
    )


client = get_api_client(st.session_state.api_base_url)
try:
    devices, groups = client.list_devices(), client.list_groups()
except ApiError as exc:
    st.error(str(exc))
    st.stop()

filters = st.container(horizontal=True)
device = filters.selectbox("Dispositivo", ["Todos", *devices], key="eda_device")
group = filters.selectbox("Grupo", ["Todos", *groups], key="eda_group")
limit = filters.slider("Muestras para analizar", 100, 5000, 1000, step=100)
selected_label = st.selectbox("Variable", list(_VARIABLES), key="eda_variable")
variable_api, variable_column, lower_bound, upper_bound, step = _VARIABLES[selected_label]
value_range = st.slider(
    f"Rango de {selected_label}",
    min_value=lower_bound,
    max_value=upper_bound,
    value=(lower_bound, upper_bound),
    step=step,
    key="eda_value_range",
)

use_dates = st.checkbox("Filtrar EDA por fechas", value=False)
from_at: str | None = None
to_at: str | None = None
if use_dates:
    dates = st.columns(2)
    start_date = dates[0].date_input("Desde", value=date.today() - timedelta(days=7))
    end_date = dates[1].date_input("Hasta", value=date.today())
    if start_date > end_date:
        st.error("La fecha inicial no puede ser posterior a la final.")
        st.stop()
    from_at = datetime.combine(start_date, time.min, timezone.utc).isoformat()
    to_at = datetime.combine(end_date, time.max, timezone.utc).isoformat()

try:
    raw_data = load_analysis_data(
        st.session_state.api_base_url,
        limit,
        None if device == "Todos" else device,
        None if group == "Todos" else group,
        from_at,
        to_at,
        variable_api,
        float(value_range[0]),
        float(value_range[1]),
    )
except ApiError as exc:
    st.error(str(exc))
    st.stop()
if raw_data.empty:
    st.info("No hay muestras que cumplan los filtros del análisis.")
    st.stop()

numeric_columns = ["soil_percent", "soil_adc", "rain_percent", "rain_adc"]
duplicates = int(raw_data.duplicated(subset=["id"]).sum())
missing_before = int(raw_data[numeric_columns].isna().sum().sum())
data = raw_data.drop_duplicates(subset=["id"]).copy()
for column in numeric_columns:
    data[column] = pd.to_numeric(data[column], errors="coerce")
data = data.dropna(subset=["fecha", *numeric_columns]).sort_values("fecha")
removed = len(raw_data) - len(data)
if data.empty:
    st.warning("La limpieza eliminó todas las filas no válidas.")
    st.stop()

st.subheader("Limpieza básica y calidad")
quality = st.columns(5)
quality[0].metric("Filas recibidas", len(raw_data))
quality[1].metric("Filas limpias", len(data))
quality[2].metric("Duplicados", duplicates)
quality[3].metric("Nulos numéricos", missing_before)
quality[4].metric("Con alertas", int(data["quality_flags"].ne("").sum()))
st.caption(
    f"Proceso reproducible: tipos numéricos normalizados, duplicados por ID eliminados "
    f"y filas incompletas descartadas. Filas retiradas: {removed}."
)

numeric = data[numeric_columns]
st.subheader("Comportamiento temporal")
st.line_chart(data.set_index("fecha")[[variable_column]], y_label=selected_label)
st.subheader("Estadísticos descriptivos")
st.dataframe(numeric.describe().T, width="stretch")
st.subheader("Matriz de correlación de Pearson")
st.dataframe(numeric.corr(method="pearson").round(3), width="stretch")

st.subheader("Distribución por intervalos")
bins = pd.cut(data[variable_column], bins=10, duplicates="drop").value_counts().sort_index()
distribution = pd.DataFrame(
    {"intervalo": bins.index.astype(str), "muestras": bins.values}
).set_index("intervalo")
st.bar_chart(distribution)

st.subheader("Valores atípicos por IQR")
q1 = data[variable_column].quantile(0.25)
q3 = data[variable_column].quantile(0.75)
iqr = q3 - q1
lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
outliers = data[(data[variable_column] < lower) | (data[variable_column] > upper)]
st.write(f"Rango esperado por IQR: `{lower:.2f}` a `{upper:.2f}`")
if outliers.empty:
    st.success("No se detectaron valores atípicos con la regla IQR.")
else:
    st.warning(f"Se detectaron {len(outliers)} valores atípicos.")
    st.dataframe(outliers, width="stretch", hide_index=True)

st.download_button(
    "Descargar CSV del EDA filtrado y limpio",
    data.to_csv(index=False).encode("utf-8-sig"),
    file_name=f"eda_filtrado_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.csv",
    mime="text/csv; charset=utf-8",
    icon=":material/download:",
    type="primary",
)
