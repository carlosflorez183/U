"""Recursos compartidos por las páginas del frontend."""

from __future__ import annotations

import streamlit as st

from api_client import RecordsApiClient


@st.cache_resource
def get_api_client(base_url: str) -> RecordsApiClient:
    """Comparte un cliente HTTP por URL de API durante la sesión de Streamlit."""
    return RecordsApiClient(base_url)
