"""Punto de entrada del dashboard agrícola IoT."""

from __future__ import annotations

import os

import streamlit as st

st.set_page_config(
    page_title="Monitoreo agrícola IoT",
    page_icon=":material/potted_plant:",
    layout="wide",
)

if "api_base_url" not in st.session_state:
    st.session_state.api_base_url = os.getenv("API_BASE_URL", "http://localhost:8000")

page = st.navigation(
    [
        st.Page("app_pages/catalog.py", title="Monitoreo", icon=":material/monitoring:"),
        st.Page("app_pages/register.py", title="Simulador ESP32", icon=":material/sensors:"),
        st.Page("app_pages/admin.py", title="Administración", icon=":material/admin_panel_settings:"),
        st.Page("app_pages/analytics.py", title="Análisis exploratorio", icon=":material/analytics:"),
        st.Page("app_pages/models.py", title="Modelos predictivos", icon=":material/model_training:"),
    ],
    position="top",
)
st.title(f"{page.icon} {page.title}")
st.caption(
    "Humedad capacitiva del suelo · Detección de lluvia · FastAPI · PostgreSQL/TimescaleDB · WebSocket"
)
page.run()
