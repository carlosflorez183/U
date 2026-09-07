# Matriz de cumplimiento del parcial IoT

Fuente: `Parcial_Integrador_Mineria_Datos_IoT.md` y `arquitectura_iot.md`.

| Requisito | Estado | Evidencia |
|---|---|---|
| ESP32 y dos sensores reales | Implementado en firmware; requiere hardware | `firmware/esp32_agro_iot/esp32_agro_iot.ino` |
| LCD I2C con dos variables y estado HTTP | Implementado; requiere prueba física | Sketch y `docs/CIRCUITO_ESP32.md` |
| Captura periódica 5/10 s | Implementado a 5 s, configurable | `SAMPLE_PERIOD_MS` |
| POST HTTP JSON autenticado | Cumplido | Firmware y `/api/v2/telemetry/samples` con `X-API-Key`/`X-Secret-Key` |
| API Python 3.10+, FastAPI y POO | Cumplido | Capas domain/application/infrastructure/api |
| Validación de tipo, rango y formato | Cumplido | Pydantic y entidades de dominio |
| PostgreSQL | Cumplido | psycopg, Compose y repositorios PostgreSQL |
| Extensión TimescaleDB | Cumplido | migración y hypertable `sensor_measurements` |
| Timestamp + grupo/dispositivo | Cumplido | esquema y contrato v2 |
| Mínimo 7 tablas relacionadas | Cumplido | 10 tablas IoT/seguridad relacionadas; 12 físicas en total |
| Filtros de fecha, rango y variable | Cumplido | Monitoreo, EDA y API |
| EDA de comportamiento/distribución/calidad | Cumplido | `analytics.py` |
| Limpieza básica | Cumplido | conversión de tipos, duplicados y nulos |
| Matriz de correlación | Cumplido | correlación Pearson dinámica |
| Anomalías | Cumplido | flags de dominio e IQR |
| Dos algoritmos ML | Cumplido | regresión lineal y k-NN con división temporal |
| Tiempo real web | Mejora cumplida | WebSocket + actualización Streamlit |
| Exportación CSV filtrada | Mejora cumplida | CSV del DataFrame visible |
| Exportaciones JSON/XLSX/PDF | Mejora cumplida | endpoints y Streamlit |
| Administración de dispositivos | Mejora cumplida | alta, listado, alias, activación y desactivación en `/api/v2/admin/*` y `admin.py` |
| Autenticación por dispositivo | Mejora cumplida | API key + secret hasheados; revalidación antes de persistir |
| Gestión de credenciales | Mejora cumplida | emisión, listado sin secretos y revocación administrativa |
| Trazabilidad de inserción | Mejora cumplida | credencial, snapshots de alias y `payload_sha256` en `telemetry_samples` |
| Idempotencia segura | Mejora cumplida | `201` nueva, `200` reintento idéntico y `409` payload diferente |
| Power BI directo a PostgreSQL | Preparado; requiere Power BI Desktop | vistas y carpeta `powerbi/` |
| `.pbix`, 4 KPIs, 6 gráficos, 2 filtros | Pendiente externo | debe generarse/validarse en Windows |
| Sustentación e interpretación | Responsabilidad del equipo | usar EDA, modelos y guía Power BI |

## Evidencia de base de datos

Las migraciones se aplican en orden:

### `001_initial.sql`

La migración detecta TimescaleDB: en el entorno Docker local crea la extensión y convierte `sensor_measurements` en hypertable; en Supabase PostgreSQL 17 crea el mismo esquema como tabla estándar indexada. También crea `legacy_records`, `schema_migrations`, catálogos, índices y vistas. Para demostrar literalmente el requisito TimescaleDB del enunciado debe usarse el entorno local o un proveedor compatible.

### `002_device_credentials.sql`

Crea `device_credentials`, añade a `telemetry_samples` la credencial de ingesta, snapshots de alias y fingerprint del payload, agrega los índices de seguridad y actualiza `vw_telemetry_wide`.

### `003_postgresql_portability.sql`

Reemplaza el resumen diario con `date_trunc` estándar y fija el día analítico en UTC. Esto actualiza también bases que ya habían aplicado la definición anterior con `time_bucket`.

El estado final contiene:

1. `iot_groups`
2. `devices`
3. `sensor_types`
4. `sensors`
5. `calibrations`
6. `telemetry_samples`
7. `sensor_measurements` — tabla PostgreSQL indexada; hypertable cuando TimescaleDB está disponible
8. `quality_flag_types`
9. `sample_quality_flags`
10. `device_credentials`
11. `legacy_records`
12. `schema_migrations`

Las primeras diez forman el grafo IoT/seguridad relacionado. El modelo documenta 12 claves foráneas; las relaciones nuevas enlazan credenciales con dispositivos y muestras. Las vistas `vw_telemetry_wide` y `vw_powerbi_daily_summary` son fuentes de consulta y Power BI.

## Seguridad y alcance real

- La ingesta requiere credenciales de dispositivo y no autoaprovisiona inventario.
- El alta y la gestión de credenciales requieren headers bootstrap de administración.
- No hay cuentas, sesiones ni roles de usuarios humanos.
- Las consultas, exportaciones y WebSocket siguen siendo públicos; producción requiere TLS y controles perimetrales.

## Lo que no puede validarse solo con software

- Cable UTP, alimentación, voltajes y funcionamiento físico.
- Calibración seca/húmeda real de ambos sensores.
- Custodia operativa de secretos en dispositivos desplegados.
- Archivo binario `.pbix`, porque Power BI Desktop no existe para macOS.
- Calidad de la sustentación y hallazgos con datos reales.
