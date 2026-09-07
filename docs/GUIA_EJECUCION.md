# Guía de ejecución

## Requisitos

- Docker Desktop y Docker Compose v2.
- Puertos 5432, 8000 y 8501 disponibles, o variables alternativas.
- `curl` para los ejemplos.

## 1. Preparar secretos y levantar la plataforma

```bash
cp .env.example .env
```

Antes de iniciar, edita `.env` y cambia obligatoriamente:

```dotenv
POSTGRES_PASSWORD=<contraseña-fuerte>
CREDENTIAL_PEPPER=<valor-aleatorio-de-al-menos-32-caracteres>
ADMIN_API_KEY=<valor-aleatorio-de-al-menos-16-caracteres>
ADMIN_SECRET_KEY=<valor-aleatorio-de-al-menos-24-caracteres>
```

No reutilices valores de ejemplo. Conserva `CREDENTIAL_PEPPER`: cambiarlo después de emitir credenciales invalida la localización de las API keys existentes.

```bash
docker compose up --build -d
docker compose ps
```

Deben quedar saludables `postgres`, `api` y `frontend`; `migrate` debe terminar con código 0 después de aplicar `001_initial.sql`, `002_device_credentials.sql` y `003_postgresql_portability.sql`.

## 2. URLs

| Servicio | Dirección |
|---|---|
| Streamlit | http://localhost:8501 |
| Swagger | http://localhost:8000/docs |
| Readiness | http://localhost:8000/health/ready |
| PostgreSQL | `localhost:5432/agro_iot` |

Puertos alternativos:

```bash
POSTGRES_PORT=15432 API_PORT=18000 FRONTEND_PORT=18501 docker compose up --build -d
```

## 3. Cargar las credenciales administrativas

Usa los mismos valores configurados en `.env`:

```bash
export ADMIN_API_KEY='<valor-de-ADMIN_API_KEY>'
export ADMIN_SECRET_KEY='<valor-de-ADMIN_SECRET_KEY>'
```

Todas las rutas administrativas requieren ambos headers. Un valor ausente o incorrecto responde `401`.

## 4. Registrar el dispositivo

La ingesta no crea dispositivos, sensores ni calibraciones. Primero registra el dispositivo mediante la API administrativa:

```bash
curl -i -X POST http://localhost:8000/api/v2/admin/devices \
  -H "Content-Type: application/json" \
  -H "X-Admin-API-Key: ${ADMIN_API_KEY}" \
  -H "X-Admin-Secret-Key: ${ADMIN_SECRET_KEY}" \
  -d '{
    "group_id":"grupo-01",
    "device_id":"esp32-grupo-01",
    "alias":"Parcela norte"
  }'
```

La creación devuelve `201`. Registrar otra vez el mismo dispositivo devuelve `409 CONFLICT`.

## 5. Emitir una credencial

```bash
curl -i -X POST http://localhost:8000/api/v2/admin/credentials \
  -H "Content-Type: application/json" \
  -H "X-Admin-API-Key: ${ADMIN_API_KEY}" \
  -H "X-Admin-Secret-Key: ${ADMIN_SECRET_KEY}" \
  -d '{
    "device_id":"esp32-grupo-01",
    "alias":"Credencial firmware"
  }'
```

La respuesta `201` muestra `api_key` y `secret_key` una sola vez y lleva `Cache-Control: no-store` y `Pragma: no-cache`. Copia ambos valores en un gestor seguro; el listado administrativo no puede recuperarlos completos.

Extracción manual:

```bash
export API_KEY='ak_copie_el_valor_de_la_respuesta'
export SECRET_KEY='sk_copie_el_valor_de_la_respuesta'
```

También puedes asignar `API_KEY` y `SECRET_KEY` mediante tu herramienta habitual de secretos. No los escribas en el repositorio ni los incluyas en capturas públicas.

## 6. Enviar una muestra autenticada

```bash
curl -i -X POST http://localhost:8000/api/v2/telemetry/samples \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${API_KEY}" \
  -H "X-Secret-Key: ${SECRET_KEY}" \
  -d '{
    "schema_version":"2.0",
    "group_id":"grupo-01",
    "device_id":"esp32-grupo-01",
    "sequence":1,
    "measured_at":"2026-09-04T14:00:00Z",
    "sampling_period_seconds":5,
    "soil_moisture":{"raw_adc":2400,"percent":45.0},
    "rain":{"raw_adc":3600,"wetness_percent":5.0,"detected":false}
  }'
```

Semántica de respuesta:

- `201`: muestra nueva, `duplicate=false`;
- `200`: mismo dispositivo, secuencia y payload, `duplicate=true`;
- `409`: mismo dispositivo/secuencia con contenido diferente; no se reemplaza la muestra original;
- `401`: claves ausentes/incorrectas, credencial revocada o dispositivo inactivo;
- `403`: credencial válida, pero el `group_id` o `device_id` del body no corresponde a ella.

Para comprobar `200`, repite exactamente el mismo comando y payload. No cambies fecha, lecturas ni periodo.

## 7. Consultar con filtros

Las consultas de lectura actuales no requieren las credenciales del dispositivo:

```bash
curl --get http://localhost:8000/api/v2/telemetry/samples \
  --data-urlencode "group_id=grupo-01" \
  --data-urlencode "variable=soil_percent" \
  --data-urlencode "min_value=30" \
  --data-urlencode "max_value=70" \
  --data-urlencode "from=2026-09-01T00:00:00Z" \
  --data-urlencode "to=2026-09-30T23:59:59Z"
```

Variables: `soil_percent`, `rain_percent`, `soil_adc`, `rain_adc`.

## 8. Streamlit

La navegación contiene cinco páginas:

- **Monitoreo:** filtros, tabla, gráficos, WebSocket y CSV exacto.
- **Simulador ESP32:** prueba ingesta con API key y secret de dispositivo.
- **Administración:** usa `X-Admin-API-Key` y `X-Admin-Secret-Key` para registrar/listar dispositivos, cambiar alias/estado y emitir/listar/revocar credenciales.
- **Análisis exploratorio:** limpieza, calidad, tendencia, distribución, correlación e IQR.
- **Modelos predictivos:** persistencia, regresión lineal y k-NN con corte temporal.

Las claves administrativas introducidas en la interfaz son secretos operativos. No las compartas ni uses la página sobre HTTP fuera del entorno local.

## 9. Inspeccionar PostgreSQL/TimescaleDB

```bash
docker compose exec postgres psql -U agro_iot -d agro_iot -c "\\dt"
docker compose exec postgres psql -U agro_iot -d agro_iot -c \
  "SELECT version, applied_at FROM schema_migrations ORDER BY version;"
docker compose exec postgres psql -U agro_iot -d agro_iot -c \
  "SELECT hypertable_name FROM timescaledb_information.hypertables;"
docker compose exec postgres psql -U agro_iot -d agro_iot -c \
  "SELECT device_id, device_alias, inserted_by_alias, measured_at FROM vw_telemetry_wide ORDER BY measured_at DESC LIMIT 5;"
```

Deben aparecer los marcadores `001_initial`, `002_device_credentials` y `003_postgresql_portability`. En el entorno Docker, `sensor_measurements` también debe aparecer como hypertable.

## 10. Exportaciones

```bash
curl -OJ "http://localhost:8000/api/v2/telemetry/export/csv?group_id=grupo-01&variable=soil_percent&min_value=30&max_value=70&limit=5000"
curl -OJ "http://localhost:8000/api/v2/telemetry/export/xlsx?limit=5000"
curl -OJ "http://localhost:8000/api/v2/telemetry/export/pdf?limit=5000"
curl -OJ "http://localhost:8000/api/v2/telemetry/export/json?limit=5000"
```

Estas rutas de lectura son públicas en la implementación actual. No expongas el servicio a Internet sin TLS, autenticación perimetral y rate limiting.

## 11. ESP32

Antes de cargar el sketch:

1. registra el dispositivo y emite una credencial;
2. configura WiFi, URL/IP LAN, `GROUP_ID`, `DEVICE_ID`, `API_KEY` y `SECRET_KEY` en `firmware/esp32_agro_iot/esp32_agro_iot.ino`;
3. revisa pines y calibraciones;
4. instala ArduinoJson, LiquidCrystal I2C y las dependencias indicadas en el README;
5. evita `localhost`: desde el ESP32 usa la IP LAN del equipo;
6. usa HTTPS y custodia segura de claves fuera de una práctica local.

El firmware envía `X-API-Key`/`X-Secret-Key`, obtiene hora NTP y persiste la secuencia en NVS. Solo avanza la secuencia con `200` o `201`. Un `409` indica que se reutilizó la secuencia con un payload distinto.

## 12. Diagnóstico y detención

Todas las respuestas incluyen `X-Request-ID`; úsalo para correlacionar el error con logs.

```bash
docker compose logs -f postgres migrate api frontend
docker compose ps
curl http://localhost:8000/health/ready
docker compose down
```

Los datos permanecen en `postgres_data`. `docker compose down -v` elimina permanentemente la base; no lo ejecutes sin respaldo.
