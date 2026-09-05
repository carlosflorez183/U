"""Monitoreo en tiempo real con filtros y exportación exacta."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pandas as pd
import streamlit as st

from api_client import ApiError
from realtime import EventListener
from services import get_api_client

_VARIABLES = {
    "Humedad del suelo (%)": ("soil_percent", "Humedad suelo (%)", 0.0, 100.0, 0.5),
    "Humedad de lluvia (%)": ("rain_percent", "Lluvia (%)", 0.0, 100.0, 0.5),
    "ADC del suelo": ("soil_adc", "ADC suelo", 0, 4095, 1),
    "ADC de lluvia": ("rain_adc", "ADC lluvia", 0, 4095, 1),
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
    st.error(str(exc))
    st.stop()

identity = st.container(horizontal=True)
selected_group = identity.selectbox("Grupo", ["Todos", *groups])
selected_device = identity.selectbox("Dispositivo", ["Todos", *devices])
limit = identity.slider("Máximo de muestras", 50, 5000, 500, step=50)
if identity.button("Actualizar", icon=":material/refresh:"):
    load_samples.clear()
    load_catalogs.clear()
    load_export.clear()

selected_variable = st.selectbox("Variable para filtrar", list(_VARIABLES))
variable, variable_column, lower_bound, upper_bound, step = _VARIABLES[selected_variable]
value_range = st.slider(
    f"Rango de {selected_variable}",
    min_value=lower_bound,
    max_value=upper_bound,
    value=(lower_bound, upper_bound),
    step=step,
)

use_dates = st.checkbox("Filtrar por fechas", value=False)
from_at: str | None = None
to_at: str | None = None
if use_dates:
    date_columns = st.columns(2)
    start_date = date_columns[0].date_input(
        "Fecha inicial", value=date.today() - timedelta(days=7)
    )
    end_date = date_columns[1].date_input("Fecha final", value=date.today())
    if start_date > end_date:
        st.error("La fecha inicial no puede ser posterior a la fecha final.")
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
        st.toast(f"{len(events)} nueva(s) muestra(s) recibida(s).")

    connection = "Conectado" if listener.is_connected else "Conectando…"
    st.caption(f"Canal WebSocket: {connection}")
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
        st.error(str(exc))
        return
    if not samples:
        st.info("No hay telemetría que cumpla todos los filtros seleccionados.")
        return

    frame = _to_frame(samples)
    latest = frame.iloc[-1]
    metrics = st.columns(4)
    metrics[0].metric("Humedad del suelo", f"{latest['Humedad suelo (%)']:.1f} %")
    metrics[1].metric("Estado del suelo", str(latest["Estado suelo"]))
    metrics[2].metric("Superficie mojada", f"{latest['Lluvia (%)']:.1f} %")
    metrics[3].metric("Lluvia", "Detectada" if latest["Lluvia detectada"] else "Sin lluvia")

    st.subheader("Series de sensores")
    st.line_chart(
        frame.set_index("Fecha")[["Humedad suelo (%)", "Lluvia (%)"]],
        y_label="Porcentaje (%)",
    )
    flagged = frame[frame["Calidad"] != "OK"]
    if flagged.empty:
        st.success("Las muestras filtradas no presentan alertas de calidad.")
    else:
        st.warning(f"Hay {len(flagged)} muestra(s) con alertas de calidad.")
        st.dataframe(flagged.tail(20), width="stretch", hide_index=True)

    visible = frame.sort_values("Fecha", ascending=False)
    st.subheader("Muestras filtradas")
    st.caption(
        f"{len(visible)} filas · {selected_variable}: {min_value:g} a {max_value:g}"
    )
    st.dataframe(visible, width="stretch", hide_index=True)

    st.subheader("Exportar telemetría filtrada")
    formats = {
        "CSV exacto de la tabla visible (.csv)": "csv",
        "Excel (.xlsx)": "xlsx",
        "PDF (.pdf)": "pdf",
        "JSON (.json)": "json",
    }
    selected_label = st.selectbox("Formato", list(formats), key="telemetry_export_format")
    export_format = formats[selected_label]
    if export_format == "csv":
        content = visible.to_csv(index=False).encode("utf-8-sig")
        filename = f"telemetria_filtrada_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.csv"
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
            st.error(str(exc))
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
        rows.append(
            {
                "ID": sample["id"],
                "Fecha": pd.to_datetime(sample["measured_at"], utc=True),
                "Grupo": sample["group_id"],
                "Dispositivo": sample["device_id"],
                "Secuencia": sample["sequence"],
                "Humedad suelo (%)": sample["soil_moisture"]["percent"],
                "ADC suelo": sample["soil_moisture"]["raw_adc"],
                "Estado suelo": sample["soil_status"],
                "Lluvia (%)": sample["rain"]["wetness_percent"],
                "ADC lluvia": sample["rain"]["raw_adc"],
                "Lluvia detectada": sample["rain"]["detected"],
                "Calidad": ", ".join(sample["quality_flags"]) or "OK",
            }
        )
    return pd.DataFrame(rows)


live_dashboard()
