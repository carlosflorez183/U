# Monitoreo agrícola IoT

Solución integral para recolectar y analizar datos de un sensor capacitivo de humedad del suelo y un sensor de lluvia conectados a un ESP32. Incluye FastAPI con DDD, PostgreSQL/TimescaleDB, Streamlit en tiempo real, exportaciones y artefactos para Power BI.

## Componentes

- `backend/`: dominio, casos de uso, API FastAPI y adaptadores PostgreSQL.
- `backend/migrations/`: esquema idempotente con 12 tablas, credenciales hasheadas y TimescaleDB.
- `frontend/`: Streamlit con filtros, WebSocket, EDA, anomalías y dos algoritmos.
- `firmware/`: sketch ESP32 con WiFi, LCD I2C y POST JSON.
- `powerbi/`: conexión, consultas y medidas para construir el `.pbix`.
- `docs/`: circuito, modelo de datos, arquitectura, ejecución y cumplimiento.

## Inicio rápido

```bash
cp .env.example .env
docker compose up --build -d
docker compose ps
```

Servicios por defecto:

- Streamlit: http://localhost:8501
- Swagger: http://localhost:8000/docs
- Readiness: http://localhost:8000/health/ready
- PostgreSQL: `localhost:5432`, base `agro_iot`

Si los puertos están ocupados:

```bash
POSTGRES_PORT=15432 API_PORT=18000 FRONTEND_PORT=18501 docker compose up --build -d
```

## Contrato principal

```text
POST /api/v2/telemetry/samples              # X-API-Key + X-Secret-Key
GET  /api/v2/telemetry/samples
GET  /api/v2/telemetry/devices
GET  /api/v2/telemetry/groups
GET  /api/v2/telemetry/export/{csv|json|xlsx|pdf}
WS   /api/v2/telemetry/events
POST /api/v2/admin/devices                    # credenciales admin
POST /api/v2/admin/credentials
```

La consulta y exportación aceptan grupo, dispositivo, fechas, variable y rango. El CSV de Streamlit se genera desde la tabla visible y contiene exactamente los filtros aplicados.

## Base de datos

El esquema contiene 12 tablas; diez forman el modelo IoT y seguridad relacionado. `device_credentials` vincula claves hasheadas con dispositivos y `telemetry_samples` conserva el alias autor. `sensor_measurements` es una hypertable TimescaleDB. `vw_telemetry_wide` es la fuente estable para API y Power BI, y `vw_powerbi_daily_summary` resume indicadores diarios.

## Documentación

- [Documentación técnica integral del código](docs/DOCUMENTACION_CODIGO.md)
- [Guía de ejecución](docs/GUIA_EJECUCION.md)
- [Arquitectura DDD](docs/ARQUITECTURA_PROYECTO.md)
- [Modelo PostgreSQL](docs/MODELO_DATOS_POSTGRESQL.md)
- [Circuito y calibración](docs/CIRCUITO_ESP32.md)
- [Contrato de telemetría](docs/CONTRATO_TELEMETRIA.md)
- [Matriz de cumplimiento](docs/ALCANCE_DOCX.md)
- [Despliegue](docs/DESPLIEGUE.md)
- [Alojamiento cloud y conexión con Power BI](docs/ALOJAMIENTO_CLOUD_POWER_BI.md)
- [Power BI](powerbi/README.md)

> El archivo `.pbix` debe abrirse y guardarse con Power BI Desktop. El repositorio incluye vistas, consultas, medidas DAX y composición, pero macOS no puede generar ni validar ese binario de Power BI Desktop.
