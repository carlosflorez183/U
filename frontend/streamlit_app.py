"""Punto de entrada del dashboard agrícola IoT."""

from __future__ import annotations

import os

import streamlit as st

from ui import apply_app_style, render_page_header

st.set_page_config(
    page_title="Estación climática DHT22",
    page_icon=":material/thermostat:",
    layout="wide",
)
apply_app_style()

if "api_base_url" not in st.session_state:
    st.session_state.api_base_url = os.getenv("API_BASE_URL", "http://localhost:8000")

page = st.navigation(
    [
        st.Page("app_pages/catalog.py", title="Monitoreo", icon=":material/monitoring:"),
        st.Page("app_pages/register.py", title="Simulador ESP32", icon=":material/sensors:"),
        st.Page(
            "app_pages/admin.py",
            title="Administración",
            icon=":material/admin_panel_settings:",
        ),
        st.Page(
            "app_pages/analytics.py",
            title="Análisis exploratorio",
            icon=":material/analytics:",
        ),
        st.Page(
            "app_pages/models.py",
            title="Modelos predictivos",
            icon=":material/model_training:",
        ),
    ],
    position="top",
)

_PAGE_HEADERS = {
    "Monitoreo": {
        "title": "Clima interior, en vivo desde el DHT22",
        "description": "Sigue temperatura y humedad del aire, controla la calidad de cada lectura y descarga el conjunto filtrado.",
        "eyebrow": "Estación climática IoT",
        "status": "Enlace activo",
    },
    "Simulador ESP32": {
        "title": "Banco de pruebas del sensor",
        "description": "Genera tramas idénticas a las del firmware para comprobar la ingesta de punta a punta.",
        "eyebrow": "Consola de validación",
        "status": "Modo prueba",
    },
    "Administración": {
        "title": "Consola de la flota DHT22",
        "description": "Da de alta nodos, emite credenciales y gestiona su estado desde un solo panel.",
        "eyebrow": "Gestión de nodos",
        "status": "Zona restringida",
    },
    "Análisis exploratorio": {
        "title": "Del registro crudo al diagnóstico",
        "description": "Limpieza, tendencia, dispersión, correlación temperatura-humedad y detección de atípicos.",
        "eyebrow": "Exploración de datos",
        "status": "EDA guiado",
    },
    "Modelos predictivos": {
        "title": "Anticipa la humedad ambiente",
        "description": "Compara persistencia, regresión lineal y k-NN sobre la serie de humedad con partición temporal.",
        "eyebrow": "Pronóstico experimental",
        "status": "Backtest temporal",
    },
}
header = _PAGE_HEADERS[page.title]
render_page_header(**header)
page.run()
