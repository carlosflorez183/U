# Recomendaciones de despliegue

Para una arquitectura concreta con Tiger Cloud, Render y conexión directa desde Power BI, consulta [Alojamiento cloud y conexión con Power BI](ALOJAMIENTO_CLOUD_POWER_BI.md).

## Antes de publicar

1. Cambia `POSTGRES_PASSWORD` y todas las credenciales del `.env`.
2. No subas `.env`, contraseñas WiFi, certificados ni secretos del firmware.
3. Usa HTTPS detrás de Caddy, Nginx, Traefik o un balanceador.
4. Habilita WebSocket Upgrade en `/api/v2/telemetry/events`.
5. Restringe `CORS_ORIGINS` al dominio real.
6. No expongas PostgreSQL a Internet salvo mediante firewall/VPN y TLS.
7. Crea un rol Power BI de sólo lectura sobre las vistas.
8. Programa copias de seguridad y prueba restauraciones de `postgres_data`.

## Base de datos

- La migración es portable: habilita TimescaleDB y convierte `sensor_measurements` en hypertable cuando la extensión está disponible; en Supabase PostgreSQL 17 conserva la misma estructura como tabla estándar indexada.
- El servicio `migrate` ejecuta en orden todos los archivos `backend/migrations/*.sql` antes de iniciar la API.
- Verifica que `schema_migrations` contenga `001_initial`, `002_device_credentials` y `003_postgresql_portability`, y que existan las dos vistas.
- En instalaciones TimescaleDB puedes ajustar chunks, compresión y retención después de medir volumen; en PostgreSQL estándar monitorea índices, tamaño y planes de consulta.
- Power BI debe leer `vw_telemetry_wide` y `vw_powerbi_daily_summary`, no tablas internas.

## Autenticación del ESP32

Cada dispositivo debe registrarse y usar una credencial diferente mediante `X-API-Key` y `X-Secret-Key`. La API key se almacena como digest HMAC con `CREDENTIAL_PEPPER`; la secret se almacena con `scrypt` y salt. Cambia `CREDENTIAL_PEPPER`, `ADMIN_API_KEY` y `ADMIN_SECRET_KEY` antes del despliegue.

Los endpoints `/api/v2/admin/*` usan las credenciales bootstrap administrativas únicamente para registrar dispositivos y emitir/revocar claves. La secret de dispositivo se entrega una sola vez. Usa HTTPS obligatoriamente fuera de localhost: los headers no están cifrados por HTTP.

Para rotar una clave, crea otra credencial vinculada, actualiza el ESP32 y revoca la anterior. Desactivar el dispositivo bloquea todas sus credenciales.

## Escalado

Mantén una réplica mientras el hub WebSocket esté en memoria. Para varias réplicas usa Redis Pub/Sub/Streams o un outbox transaccional.

## Observabilidad

- Alerta cuando `/health/ready` falle.
- Mide muestras/minuto, latencia `received_at - measured_at`, duplicados y flags.
- Centraliza logs de API, frontend y PostgreSQL.
- Controla conexiones del pool, tamaño de tablas e índices; si TimescaleDB está activo, controla también sus chunks.

## Verificación previa a entrega

```bash
docker compose config --quiet
docker compose up --build -d
docker compose ps
curl -f http://localhost:8000/health/ready
docker compose exec postgres psql -U agro_iot -d agro_iot -c \
  "SELECT version FROM schema_migrations ORDER BY version;"
```

Entrega recomendada: repositorio Git sin secretos, tag de versión, capturas, evidencia de calibración, diagrama de circuito, exportación de muestra y `.pbix` validado en Windows.
