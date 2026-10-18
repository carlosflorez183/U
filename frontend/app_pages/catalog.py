"""Monitoreo en tiempo real con filtros y exportación exacta."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pandas as pd
import streamlit as st

from api_client import ApiError
from realtime import EventListener
from services import get_api_client
from ui import COLORS, render_empty_state, render_section_intro, render_status

_VARIABLES = {
    "Temperatura (°C)": ("temperature", "Temperatura (°C)", -40.0, 80.0, 0.5),
    "Humedad relativa (%)": ("humidity", "Humedad (%)", 0.0, 100.0, 0.5),
}


@st.cache_data(ttl=30, show_spinner="Consultando sensores...")
def load_samples(
    api_base_url: str,
    limit: int,
    device_id: str | None,
    group_id: str | None,
    from_at: str | None,
    to_at: str | None,
    variable: str,
    min_value: float,
    max_value: float,
) -> list[dict]:
    return get_api_client(api_base_url).list_telemetry(
        limit=limit,
        device_id=device_id,
        group_id=group_id,
        from_at=from_at,
        to_at=to_at,
        variable=variable,
        min_value=min_value,
        max_value=max_value,
    )


@st.cache_data(ttl=30)
def load_catalogs(api_base_url: str) -> tuple[list[str], list[str]]:
    client = get_api_client(api_base_url)
    return client.list_devices(), client.list_groups()


@st.cache_data(ttl=60, show_spinner="Generando exportación...")
def load_export(
    api_base_url: str,
    export_format: str,
    limit: int,
    device_id: str | None,
    group_id: str | None,
    from_at: str | None,
    to_at: str | None,
    variable: str,
    min_value: float,
    max_value: float,
) -> tuple[bytes, str, str]:
    return get_api_client(api_base_url).export_telemetry(
        export_format,
        limit=limit,
        device_id=device_id,
        group_id=group_id,
        from_at=from_at,
        to_at=to_at,
        variable=variable,
        min_value=min_value,
        max_value=max_value,
    )


def get_listener(api_base_url: str) -> EventListener:
    listener = st.session_state.get("telemetry_event_listener")
    if listener is None or listener.api_base_url != api_base_url.rstrip("/"):
        if listener is not None:
            listener.close()
        listener = EventListener(api_base_url)
        listener.start()
        st.session_state.telemetry_event_listener = listener
    return listener


try:
    devices, groups = load_catalogs(st.session_state.api_base_url)
except ApiError as exc:
    st.error("No fue posible cargar los dispositivos y grupos.", icon=":material/cloud_off:")
    st.caption(str(exc))
    st.stop()

with st.container(border=True):
    render_section_intro(
        "Filtros de monitoreo",
        "Acota el origen, volumen y rango de las muestras sin interrumpir el canal en vivo.",
    )
    identity = st.columns([1, 1, 2, 0.65], vertical_alignment="bottom")
    selected_group = identity[0].selectbox(
        "Grupo", ["Todos", *groups], key="catalog_group"
    )
    selected_device = identity[1].selectbox(
        "Dispositivo", ["Todos", *devices], key="catalog_device"
    )
    limit = identity[2].slider(
        "Máximo de muestras", 50, 5000, 500, step=50, key="catalog_limit"
    )
    if identity[3].button(
        "Actualizar",
        icon=":material/refresh:",
        key="catalog_refresh",
        width="stretch",
    ):
        load_samples.clear()
        load_catalogs.clear()
        load_export.clear()

    range_columns = st.columns([1, 2])
    selected_variable = range_columns[0].selectbox(
        "Variable para filtrar", list(_VARIABLES), key="catalog_variable"
    )
    variable, variable_column, lower_bound, upper_bound, step = _VARIABLES[
        selected_variable
    ]
    value_range = range_columns[1].slider(
        f"Rango de {selected_variable}",
        min_value=lower_bound,
        max_value=upper_bound,
        value=(lower_bound, upper_bound),
        step=step,
        key="catalog_value_range",
    )

    use_dates = st.checkbox(
        "Filtrar por fechas", value=False, key="catalog_use_dates"
    )
    from_at: str | None = None
    to_at: str | None = None
    if use_dates:
        date_columns = st.columns(2)
        start_date = date_columns[0].date_input(
            "Fecha inicial",
            value=date.today() - timedelta(days=7),
            key="catalog_start_date",
        )
        end_date = date_columns[1].date_input(
            "Fecha final", value=date.today(), key="catalog_end_date"
        )
        if start_date > end_date:
            st.error(
                "La fecha inicial no puede ser posterior a la fecha final.",
                icon=":material/event_busy:",
            )
            st.stop()
        from_at = datetime.combine(start_date, time.min, timezone.utc).isoformat()
        to_at = datetime.combine(end_date, time.max, timezone.utc).isoformat()

device_filter = None if selected_device == "Todos" else selected_device
group_filter = None if selected_group == "Todos" else selected_group
min_value, max_value = float(value_range[0]), float(value_range[1])
listener = get_listener(st.session_state.api_base_url)


@st.fragment(run_every=1)
def live_dashboard() -> None:
    events = listener.drain()
    if events:
        load_samples.clear()
        load_catalogs.clear()
        load_export.clear()

    try:
        samples = load_samples(
            st.session_state.api_base_url,
            limit,
            device_filter,
            group_filter,
            from_at,
            to_at,
            variable,
            min_value,
            max_value,
        )
    except ApiError as exc:
        st.error("No fue posible actualizar la telemetría.", icon=":material/cloud_off:")
        st.caption(str(exc))
        return

    if not samples:
        with st.container(border=True):
            render_status(
                "Canal WebSocket conectado" if listener.is_connected else "Reconectando canal WebSocket",
                "La vista se actualizará cuando lleguen nuevas muestras.",
                tone="positive" if listener.is_connected else "warning",
            )
            st.divider()
            render_empty_state(
                "No hay muestras para esta combinación",
                "Amplía el rango, cambia el dispositivo o retira el filtro de fechas para continuar.",
            )
        return

    frame = _to_frame(samples)
    latest = frame.iloc[-1]
    previous = frame.iloc[-2] if len(frame) > 1 else None
    comparable_previous = bool(
        previous is not None
        and latest["Dispositivo"] == previous["Dispositivo"]
        and latest["Secuencia"] == previous["Secuencia"] + 1
    )
    latest_time = latest["Fecha"].strftime("%d/%m/%Y · %H:%M:%S UTC")

    with st.container(border=True):
        status_columns = st.columns(2)
        with status_columns[0]:
            render_status(
                "Canal WebSocket conectado" if listener.is_connected else "Reconectando canal WebSocket",
                (
                    f"{len(events)} muestra(s) nueva(s) incorporada(s)."
                    if events
                    else "Escuchando nuevas muestras en segundo plano."
                ),
                tone="positive" if listener.is_connected else "warning",
            )
        with status_columns[1]:
            render_status(
                "Última muestra",
                f"{latest_time} · {latest['Dispositivo']}",
                tone="neutral",
            )

    temp_delta = (
        f"{latest['Temperatura (°C)'] - previous['Temperatura (°C)']:+.1f} °C"
        if comparable_previous
        else None
    )
    hum_delta = (
        f"{latest['Humedad (%)'] - previous['Humedad (%)']:+.1f} pp"
        if comparable_previous
        else None
    )
    _ESTADOS_ES = {
        "COLD": "Frío",
        "COMFORT": "Confortable",
        "HOT": "Caliente",
        "DRY": "Seco",
        "HUMID": "Húmedo",
    }
    estado_temp = _ESTADOS_ES.get(str(latest["Estado temp."]), str(latest["Estado temp."]))
    estado_hum = _ESTADOS_ES.get(str(latest["Estado humedad"]), str(latest["Estado humedad"]))
    metrics = st.columns(4)
    metrics[0].metric(
        "Temperatura",
        f"{latest['Temperatura (°C)']:.1f} °C",
        delta=temp_delta,
        border=True,
    )
    metrics[1].metric(
        "Estado temp.",
        estado_temp,
        delta=f"Secuencia {latest['Secuencia']}",
        delta_color="off",
        border=True,
    )
    metrics[2].metric(
        "Humedad relativa",
        f"{latest['Humedad (%)']:.1f} %",
        delta=hum_delta,
        border=True,
    )
    metrics[3].metric(
        "Estado humedad",
        estado_hum,
        delta="Estado actual",
        delta_color="off",
        border=True,
    )

    visible = frame.sort_values("Fecha", ascending=False)
    flagged = frame[frame["Calidad"] != "OK"]
    chart_tab, data_tab, quality_tab, export_tab = st.tabs(
        [
            ":material/show_chart: Gráfica",
            ":material/table_rows: Datos",
            ":material/verified: Calidad",
            ":material/download: Exportación",
        ]
    )

    with chart_tab:
        render_section_intro(
            "Series DHT22",
            "Verde para temperatura y azul para humedad relativa del aire.",
        )
        st.line_chart(
            frame.set_index("Fecha")[["Temperatura (°C)", "Humedad (%)"]],
            color=[COLORS["soil"], COLORS["rain"]],
        )

    with data_tab:
        render_section_intro(
            "Muestras filtradas",
            f"{len(visible)} filas · {selected_variable}: {min_value:g} a {max_value:g}",
        )
        st.dataframe(visible, width="stretch", hide_index=True)

    with quality_tab:
        render_section_intro(
            "Calidad de captura",
            "Revisa las banderas reportadas por los dispositivos en el conjunto visible.",
        )
        if flagged.empty:
            render_status(
                "Sin alertas de calidad",
                "Todas las muestras filtradas están marcadas como OK.",
                tone="neutral",
            )
        else:
            st.warning(
                f"Hay {len(flagged)} muestra(s) con alertas de calidad.",
                icon=":material/warning:",
            )
            st.dataframe(flagged.tail(20), width="stretch", hide_index=True)

    with export_tab:
        render_section_intro(
            "Exportar telemetría filtrada",
            "El CSV reproduce la tabla visible; los demás formatos se generan desde la API.",
        )
        formats = {
            "CSV exacto de la tabla visible (.csv)": "csv",
            "Excel (.xlsx)": "xlsx",
            "PDF (.pdf)": "pdf",
            "JSON (.json)": "json",
        }
        selected_label = st.selectbox(
            "Formato", list(formats), key="telemetry_export_format"
        )
        export_format = formats[selected_label]
        if export_format == "csv":
            content = visible.to_csv(index=False).encode("utf-8-sig")
            filename = (
                f"telemetria_filtrada_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.csv"
            )
            media_type = "text/csv; charset=utf-8"
        else:
            try:
                content, filename, media_type = load_export(
                    st.session_state.api_base_url,
                    export_format,
                    limit,
                    device_filter,
                    group_filter,
                    from_at,
                    to_at,
                    variable,
                    min_value,
                    max_value,
                )
            except ApiError as exc:
                st.error(
                    "No fue posible preparar la exportación.",
                    icon=":material/file_export_off:",
                )
                st.caption(str(exc))
                return
        st.download_button(
            "Descargar datos con filtros aplicados",
            content,
            file_name=filename,
            mime=media_type,
            icon=":material/download:",
            type="primary",
            key=f"iot_download_{export_format}_{len(visible)}",
        )


def _to_frame(samples: list[dict]) -> pd.DataFrame:
    rows = []
    for sample in reversed(samples):
        ambient = sample.get("ambient") or {}
        # Compat con API antigua suelo/lluvia.
        if not ambient:
            soil = sample.get("soil_moisture") or {}
            rain = sample.get("rain") or {}
            ambient = {
                "temperature_celsius": 22.0,
                "humidity_percent": float(soil.get("percent", rain.get("wetness_percent", 0.0))),
            }
        _es = {
            "COLD": "Frío",
            "COMFORT": "Confortable",
            "HOT": "Caliente",
            "DRY": "Seco",
            "HUMID": "Húmedo",
        }
        estado_temp = sample.get("temp_status", sample.get("soil_status", ""))
        estado_hum = sample.get("humidity_status", sample.get("soil_status", ""))
        rows.append(
            {
                "ID": sample["id"],
                "Fecha": pd.to_datetime(sample["measured_at"], utc=True),
                "Grupo": sample["group_id"],
                "Dispositivo": sample["device_id"],
                "Secuencia": sample["sequence"],
                "Temperatura (°C)": float(ambient.get("temperature_celsius", 0.0)),
                "Humedad (%)": float(ambient.get("humidity_percent", 0.0)),
                "Estado temp.": _es.get(str(estado_temp), str(estado_temp)),
                "Estado humedad": _es.get(str(estado_hum), str(estado_hum)),
                "Calidad": ", ".join(sample.get("quality_flags", [])) or "OK",
            }
        )
    return pd.DataFrame(rows)


live_dashboard()
