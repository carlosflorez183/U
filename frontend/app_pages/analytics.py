"""EDA, limpieza y anomalías sobre los datos filtrados."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pandas as pd
import streamlit as st

from api_client import ApiError
from services import get_api_client
from ui import COLORS, render_empty_state, render_section_intro, render_status

_VARIABLES = {
    "Temperatura (°C)": ("temperature", "temperature", -40.0, 80.0, 0.5),
    "Humedad relativa (%)": ("humidity", "humidity", 0.0, 100.0, 0.5),
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
    def _ambient(item: dict) -> dict:
        amb = item.get("ambient") or {}
        if amb:
            return amb
        soil = item.get("soil_moisture") or {}
        rain = item.get("rain") or {}
        return {
            "temperature_celsius": 22.0,
            "humidity_percent": float(
                soil.get("percent", rain.get("wetness_percent", 0.0))
            ),
        }

    return pd.DataFrame(
        [
            {
                "id": item["id"],
                "fecha": pd.to_datetime(item["measured_at"], utc=True),
                "grupo": item["group_id"],
                "dispositivo": item["device_id"],
                "temperature": float(_ambient(item).get("temperature_celsius", 0.0)),
                "humidity": float(_ambient(item).get("humidity_percent", 0.0)),
                "quality_flags": ",".join(item.get("quality_flags", [])),
            }
            for item in reversed(samples)
        ]
    )


def _correlation_cell_style(value: float) -> str:
    """Genera un gradiente verde/azul sin dependencias gráficas adicionales."""

    if pd.isna(value):
        return f"background-color: {COLORS['surface']}; color: {COLORS['muted']}"
    strength = 0.08 + (0.32 * min(abs(float(value)), 1.0))
    color = "47, 107, 69" if value >= 0 else "47, 111, 163"
    return f"background-color: rgba({color}, {strength:.2f}); color: {COLORS['ink']}"


client = get_api_client(st.session_state.api_base_url)
try:
    devices, groups = client.list_devices(), client.list_groups()
except ApiError as exc:
    st.error("No fue posible cargar los filtros del análisis.", icon=":material/cloud_off:")
    st.caption(str(exc))
    st.stop()

with st.container(border=True):
    render_section_intro(
        "Panel de análisis",
        "Define el conjunto de trabajo antes de limpiar, resumir y explorar las mediciones.",
    )
    filters = st.columns([1, 1, 2])
    device = filters[0].selectbox(
        "Dispositivo", ["Todos", *devices], key="eda_device"
    )
    group = filters[1].selectbox("Grupo", ["Todos", *groups], key="eda_group")
    limit = filters[2].slider(
        "Muestras para analizar",
        100,
        5000,
        1000,
        step=100,
        key="eda_limit",
    )
    range_columns = st.columns([1, 2])
    selected_label = range_columns[0].selectbox(
        "Variable", list(_VARIABLES), key="eda_variable"
    )
    variable_api, variable_column, lower_bound, upper_bound, step = _VARIABLES[
        selected_label
    ]
    value_range = range_columns[1].slider(
        f"Rango de {selected_label}",
        min_value=lower_bound,
        max_value=upper_bound,
        value=(lower_bound, upper_bound),
        step=step,
        key="eda_value_range",
    )

    use_dates = st.checkbox(
        "Filtrar EDA por fechas", value=False, key="eda_use_dates"
    )
    from_at: str | None = None
    to_at: str | None = None
    if use_dates:
        dates = st.columns(2)
        start_date = dates[0].date_input(
            "Desde", value=date.today() - timedelta(days=7), key="eda_start_date"
        )
        end_date = dates[1].date_input(
            "Hasta", value=date.today(), key="eda_end_date"
        )
        if start_date > end_date:
            st.error(
                "La fecha inicial no puede ser posterior a la final.",
                icon=":material/event_busy:",
            )
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
    st.error("No fue posible preparar el análisis.", icon=":material/cloud_off:")
    st.caption(str(exc))
    st.stop()
if raw_data.empty:
    render_empty_state(
        "No hay muestras para analizar",
        "Prueba otro dispositivo, amplía el rango de la variable o retira el filtro de fechas.",
    )
    st.stop()

numeric_columns = ["temperature", "humidity"]
duplicates = int(raw_data.duplicated(subset=["id"]).sum())
missing_before = int(raw_data[numeric_columns].isna().sum().sum())
data = raw_data.drop_duplicates(subset=["id"]).copy()
for column in numeric_columns:
    data[column] = pd.to_numeric(data[column], errors="coerce")
data = data.dropna(subset=["fecha", *numeric_columns]).sort_values("fecha")
removed = len(raw_data) - len(data)
if data.empty:
    st.warning(
        "La limpieza eliminó todas las filas no válidas.",
        icon=":material/filter_alt_off:",
    )
    st.caption("Revisa el origen o amplía los filtros para obtener datos utilizables.")
    st.stop()

render_section_intro(
    "Limpieza básica y calidad",
    "Tipos numéricos normalizados, duplicados por ID eliminados y filas incompletas descartadas.",
)
quality = st.columns(5)
quality[0].metric(
    "Filas recibidas", len(raw_data), delta="Entrada", delta_color="off", border=True
)
quality[1].metric(
    "Filas limpias",
    len(data),
    delta=f"{removed} retiradas",
    delta_color="off",
    border=True,
)
quality[2].metric(
    "Duplicados", duplicates, delta="Por ID", delta_color="off", border=True
)
quality[3].metric(
    "Nulos numéricos",
    missing_before,
    delta="Antes de limpiar",
    delta_color="off",
    border=True,
)
quality[4].metric(
    "Con alertas",
    int(data["quality_flags"].ne("").sum()),
    delta="Calidad",
    delta_color="off",
    border=True,
)

numeric = data[numeric_columns]
q1 = data[variable_column].quantile(0.25)
q3 = data[variable_column].quantile(0.75)
iqr = q3 - q1
lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
outliers = data[(data[variable_column] < lower) | (data[variable_column] > upper)]
series_color = COLORS["soil"] if variable_column.startswith("temp") else COLORS["rain"]

temporal_tab, stats_tab, correlation_tab, distribution_tab, outliers_tab = st.tabs(
    [
        ":material/timeline: Temporal",
        ":material/functions: Estadísticos",
        ":material/grid_on: Correlación",
        ":material/bar_chart: Distribución",
        ":material/manage_search: Atípicos",
    ]
)

with temporal_tab:
    render_section_intro(
        "Comportamiento temporal",
        f"Evolución cronológica de {selected_label.lower()} en el conjunto limpio.",
    )
    st.line_chart(
        data.set_index("fecha")[[variable_column]],
        y_label=selected_label,
        color=[series_color],
    )

with stats_tab:
    render_section_intro(
        "Estadísticos descriptivos",
        "Resumen de tendencia central, dispersión y cuantiles para las cuatro mediciones.",
    )
    st.dataframe(numeric.describe().T, width="stretch")

with correlation_tab:
    render_section_intro(
        "Matriz de correlación de Pearson",
        "Verde indica relación positiva y azul relación negativa; la intensidad expresa magnitud.",
    )
    correlation = numeric.corr(method="pearson").round(3)
    correlation_style = correlation.style.map(_correlation_cell_style).format(
        "{:.3f}", na_rep="—"
    )
    st.dataframe(correlation_style, width="stretch")

with distribution_tab:
    render_section_intro(
        "Distribución por intervalos",
        f"Frecuencia de {selected_label.lower()} agrupada en hasta diez rangos.",
    )
    bins = (
        pd.cut(data[variable_column], bins=10, duplicates="drop")
        .value_counts()
        .sort_index()
    )
    distribution = pd.DataFrame(
        {"intervalo": bins.index.astype(str), "muestras": bins.values}
    ).set_index("intervalo")
    st.bar_chart(distribution, color=[series_color])

with outliers_tab:
    render_section_intro(
        "Valores atípicos por IQR",
        f"Rango esperado: {lower:.2f} a {upper:.2f} para {selected_label.lower()}.",
    )
    if outliers.empty:
        render_status(
            "Sin valores atípicos",
            "La regla IQR 1.5 no detectó observaciones fuera del rango esperado.",
            tone="neutral",
        )
    else:
        st.warning(
            f"Se detectaron {len(outliers)} valores atípicos.",
            icon=":material/warning:",
        )
        st.dataframe(outliers, width="stretch", hide_index=True)

st.download_button(
    "Descargar CSV del EDA filtrado y limpio",
    data.to_csv(index=False).encode("utf-8-sig"),
    file_name=f"eda_filtrado_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.csv",
    mime="text/csv; charset=utf-8",
    icon=":material/download:",
    type="primary",
    key="eda_download_csv",
)
