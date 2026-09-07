"""Punto de entrada del dashboard agrícola IoT."""

from __future__ import annotations

import os

import streamlit as st

from ui import apply_app_style, render_page_header

st.set_page_config(
    page_title="Monitoreo agrícola IoT",
    page_icon=":material/potted_plant:",
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
        "title": "El campo, medido en tiempo real",
        "description": "Supervisa humedad del suelo y lluvia, revisa la calidad de cada muestra y exporta exactamente el conjunto filtrado.",
        "eyebrow": "Observatorio agrícola IoT",
        "status": "Telemetría en vivo",
    },
    "Simulador ESP32": {
        "title": "Simula lecturas antes de desplegar",
        "description": "Envía muestras compatibles con el dispositivo para validar el flujo de captura de extremo a extremo.",
        "eyebrow": "Laboratorio de dispositivos",
        "status": "Entorno controlado",
    },
    "Administración": {
        "title": "Gestiona la red de sensores",
        "description": "Administra dispositivos, credenciales y disponibilidad desde un espacio operativo unificado.",
        "eyebrow": "Operación IoT",
        "status": "Acceso administrativo",
    },
    "Análisis exploratorio": {
        "title": "Convierte las mediciones en evidencia",
        "description": "Explora tendencias, distribución, correlaciones y valores atípicos sobre datos limpios y reproducibles.",
        "eyebrow": "Analítica agrícola",
        "status": "EDA reproducible",
    },
    "Modelos predictivos": {
        "title": "Evalúa señales de lluvia futura",
        "description": "Estima una confirmación futura de lluvia a partir de la dinámica temporal del suelo y audita el resultado con el sensor de lluvia.",
        "eyebrow": "Experimento temporal",
        "status": "Sin fuga de etiqueta",
    },
}
header = _PAGE_HEADERS[page.title]
render_page_header(**header)
page.run()
