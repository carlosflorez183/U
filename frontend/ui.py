"""Sistema visual compartido para el frontend Streamlit.

Este módulo contiene únicamente tokens, estilos y helpers de presentación.
"""

from __future__ import annotations

from html import escape
from typing import Final

import streamlit as st

COLORS: Final[dict[str, str]] = {
    "soil": "#2F6B45",
    "soil_soft": "#E7F0E6",
    "rain": "#2F6FA3",
    "rain_soft": "#E5EFF7",
    "sun": "#C58A2A",
    "danger": "#B44A3A",
    "ink": "#1F2A22",
    "muted": "#647067",
    "canvas": "#FBF8F1",
    "surface": "#F1F4EA",
    "border": "#D8E0D3",
}

_STATUS_ICONS: Final[dict[str, str]] = {
    "neutral": "●",
    "positive": "●",
    "warning": "▲",
    "danger": "●",
}


def apply_app_style() -> None:
    """Aplica una capa visual estable sobre el tema nativo de Streamlit."""

    st.markdown(
        """
        <style>
        :root {
            --agri-soil: #2F6B45;
            --agri-rain: #2F6FA3;
            --agri-sun: #C58A2A;
            --agri-ink: #1F2A22;
            --agri-muted: #647067;
            --agri-canvas: #FBF8F1;
            --agri-surface: #F1F4EA;
            --agri-border: #D8E0D3;
        }

        [data-testid="stAppViewContainer"] {
            background:
                radial-gradient(circle at 92% 2%, rgba(197, 138, 42, 0.10), transparent 24rem),
                var(--agri-canvas);
        }

        [data-testid="stHeader"] {
            background: rgba(251, 248, 241, 0.92);
            border-bottom: 1px solid rgba(216, 224, 211, 0.8);
        }

        [data-testid="stMainBlockContainer"] {
            max-width: 1480px;
            padding-top: 1.5rem;
            padding-bottom: 3rem;
        }

        [data-testid="stVerticalBlockBorderWrapper"] {
            background: rgba(255, 255, 255, 0.62);
            box-shadow: 0 8px 24px rgba(31, 42, 34, 0.035);
        }

        [data-testid="stMetric"] {
            background: rgba(255, 255, 255, 0.72);
            box-shadow: 0 5px 16px rgba(31, 42, 34, 0.04);
        }

        [data-testid="stMetricLabel"] {
            color: var(--agri-muted);
        }

        [data-testid="stTabs"] button[role="tab"] {
            min-height: 2.75rem;
            font-weight: 650;
        }

        [data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
            color: var(--agri-soil);
        }

        .agri-hero {
            position: relative;
            overflow: hidden;
            padding: clamp(1.35rem, 3vw, 2.25rem);
            margin: 0.25rem 0 1.35rem;
            border: 1px solid var(--agri-border);
            border-radius: 1rem;
            background:
                linear-gradient(120deg, rgba(255, 255, 255, 0.94), rgba(231, 240, 230, 0.86)),
                var(--agri-surface);
            box-shadow: 0 14px 36px rgba(47, 107, 69, 0.08);
        }

        .agri-hero::after {
            content: "";
            position: absolute;
            width: 12rem;
            height: 12rem;
            right: -4rem;
            top: -5rem;
            border-radius: 50%;
            background: rgba(47, 111, 163, 0.09);
        }

        .agri-hero__topline {
            display: flex;
            align-items: center;
            gap: 0.7rem;
            flex-wrap: wrap;
            margin-bottom: 0.55rem;
        }

        .agri-hero__eyebrow {
            color: var(--agri-soil);
            font-size: 0.78rem;
            font-weight: 750;
            letter-spacing: 0.09em;
            text-transform: uppercase;
        }

        .agri-hero__status {
            padding: 0.25rem 0.55rem;
            border: 1px solid rgba(47, 107, 69, 0.22);
            border-radius: 999px;
            color: var(--agri-soil);
            background: rgba(231, 240, 230, 0.76);
            font-size: 0.75rem;
            font-weight: 700;
        }

        .agri-hero h1 {
            position: relative;
            z-index: 1;
            max-width: 54rem;
            margin: 0;
            color: var(--agri-ink);
            font-size: clamp(1.85rem, 4vw, 3rem);
            line-height: 1.08;
            letter-spacing: -0.035em;
        }

        .agri-hero p {
            position: relative;
            z-index: 1;
            max-width: 58rem;
            margin: 0.75rem 0 0;
            color: var(--agri-muted);
            font-size: 1rem;
            line-height: 1.6;
        }

        .agri-section-intro {
            margin: 0.25rem 0 0.8rem;
        }

        .agri-section-intro strong {
            display: block;
            color: var(--agri-ink);
            font-size: 1.05rem;
        }

        .agri-section-intro span {
            color: var(--agri-muted);
            font-size: 0.88rem;
        }

        .agri-status {
            display: flex;
            align-items: flex-start;
            gap: 0.55rem;
            color: var(--agri-muted);
            line-height: 1.4;
        }

        .agri-status__icon {
            color: var(--agri-rain);
            font-size: 0.72rem;
            line-height: 1.7;
        }

        .agri-status--positive .agri-status__icon { color: var(--agri-soil); }
        .agri-status--warning .agri-status__icon { color: var(--agri-sun); }
        .agri-status--danger .agri-status__icon { color: #B44A3A; }
        .agri-status strong { color: var(--agri-ink); }
        .agri-status small { display: block; margin-top: 0.1rem; color: var(--agri-muted); }

        .agri-empty {
            padding: 1rem 1.1rem;
            border: 1px dashed var(--agri-border);
            border-radius: 0.8rem;
            background: rgba(241, 244, 234, 0.7);
        }

        .agri-empty strong { color: var(--agri-ink); }
        .agri-empty p { margin: 0.2rem 0 0; color: var(--agri-muted); }

        @media (max-width: 700px) {
            [data-testid="stMainBlockContainer"] { padding-top: 1rem; }
            .agri-hero { padding: 1.2rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_page_header(
    title: str,
    description: str,
    eyebrow: str | None = None,
    status: str | None = None,
) -> None:
    """Renderiza una cabecera de página escapando todo el texto recibido."""

    eyebrow_html = (
        f'<span class="agri-hero__eyebrow">{escape(eyebrow)}</span>' if eyebrow else ""
    )
    status_html = (
        f'<span class="agri-hero__status">{escape(status)}</span>' if status else ""
    )
    st.markdown(
        f"""
        <section class="agri-hero">
            <div class="agri-hero__topline">{eyebrow_html}{status_html}</div>
            <h1>{escape(title)}</h1>
            <p>{escape(description)}</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_section_intro(title: str, description: str) -> None:
    """Presenta el título y la ayuda breve de una sección."""

    st.markdown(
        f"""
        <div class="agri-section-intro">
            <strong>{escape(title)}</strong>
            <span>{escape(description)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_status(
    label: str,
    detail: str | None = None,
    *,
    tone: str = "neutral",
) -> None:
    """Muestra un estado compacto y no intrusivo."""

    safe_tone = tone if tone in _STATUS_ICONS else "neutral"
    detail_html = f"<small>{escape(detail)}</small>" if detail else ""
    st.markdown(
        f"""
        <div class="agri-status agri-status--{safe_tone}">
            <span class="agri-status__icon" aria-hidden="true">{_STATUS_ICONS[safe_tone]}</span>
            <span><strong>{escape(label)}</strong>{detail_html}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_empty_state(title: str, description: str) -> None:
    """Renderiza un estado vacío neutro con texto seguro."""

    st.markdown(
        f"""
        <div class="agri-empty" role="status">
            <strong>{escape(title)}</strong>
            <p>{escape(description)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
