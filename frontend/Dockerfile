FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_HEADLESS=true

WORKDIR /app
COPY frontend/requirements-frontend.txt ./requirements-frontend.txt
RUN python -m pip install --no-cache-dir -r requirements-frontend.txt \
    && useradd --create-home --uid 10001 appuser
COPY --chown=appuser:appuser frontend ./

USER appuser
EXPOSE 8501
CMD ["streamlit", "run", "streamlit_app.py", "--server.address", "0.0.0.0", "--server.port", "8501"]
