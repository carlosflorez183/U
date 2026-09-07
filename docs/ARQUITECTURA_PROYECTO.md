# Arquitectura DDD del proyecto IoT

## Flujo general

```mermaid
flowchart LR
  ADMIN[Administrador] -->|headers bootstrap| APIA[API /api/v2/admin]
  APIA --> AS[AdminService]
  AS --> AR[AdminRepository]
  AR --> PG[(PostgreSQL)]

  S1[Sensor capacitivo] --> ESP[ESP32]
  S2[Sensor de lluvia] --> ESP
  ESP --> LCD[LCD I2C 16x2]
  ESP -->|POST JSON + X-API-Key/X-Secret-Key| AUTH[IngestAuthenticator]
  AUTH --> API[FastAPI v2]
  API --> APP[TelemetryService]
  APP --> DOM[Dominio]
  APP --> PORT[TelemetryRepository]
  PORT --> PG
  PG --- MODE[Tabla PostgreSQL<br/>hypertable opcional]
  API -->|WebSocket después del commit| ST[Streamlit]
  ST -->|lectura, exportación y administración| API
  PG -->|vistas SQL| PBI[Power BI]
```

La administración registra primero el dispositivo y su inventario, y después emite una credencial. Solo entonces el ESP32 puede enviar telemetría.

## Capas y componentes

- **Dominio:** `TelemetrySample`, lecturas de suelo/lluvia, `IngestPrincipal`, errores de autenticación/autorización/conflicto e interfaces de repositorio.
- **Aplicación:** `TelemetryService`, `AdminService`, comandos y filtros; orquesta reglas sin depender de FastAPI ni psycopg.
- **Infraestructura:** pool psycopg, `PostgresTelemetryRepository`, `PostgresAdminRepository`, hashing HMAC/scrypt, autenticadores, PostgreSQL portable con TimescaleDB opcional y renderizadores.
- **API:** routers de telemetría, administración y compatibilidad; DTO estrictos, dependencias, middleware y WebSocket.
- **Presentación:** Streamlit con cinco páginas y firmware ESP32 autenticado.

La dirección de dependencias sigue API → aplicación → dominio; infraestructura implementa los puertos del dominio y se compone en `main.py`.

## Administración y seguridad

`/api/v2/admin/*` exige:

```http
X-Admin-API-Key: <ADMIN_API_KEY>
X-Admin-Secret-Key: <ADMIN_SECRET_KEY>
```

La administración permite:

- registrar/listar dispositivos;
- activar, desactivar y cambiar alias;
- emitir/listar/revocar credenciales.

El registro administrativo crea grupo, dispositivo, sensores y calibraciones iniciales dentro de una transacción. La emisión devuelve la API key y el secret completos solo una vez; PostgreSQL conserva digest, prefijo, salt y hash.

La ingesta exige:

```http
X-API-Key: ak_...
X-Secret-Key: sk_...
```

No hay usuarios humanos, sesiones ni roles persistidos. Las credenciales bootstrap protegen administración y las credenciales por dispositivo protegen ingesta.

## Persistencia transaccional de una muestra

Una ingesta ejecuta este flujo:

1. autentica inicialmente la API key y el secret y obtiene un principal sin secretos;
2. valida que grupo/dispositivo del payload coincidan con la credencial;
3. calcula el fingerprint canónico del payload;
4. abre transacción y revalida credencial activa, revocación y dispositivo activo con bloqueo compartido;
5. vuelve a autorizar identidad y grupo;
6. actualiza `last_seen_at` e inserta la cabecera con credencial, snapshots de alias y `payload_sha256`;
7. resuelve sensores y calibraciones **ya registrados**; nunca autoaprovisiona durante ingesta;
8. inserta dos filas en `sensor_measurements` y las banderas de calidad si la muestra es nueva;
9. confirma la transacción y solo después publica el evento WebSocket.

Idempotencia:

- `201`: secuencia nueva;
- `200`: misma secuencia y fingerprint, sin duplicar detalles ni evento;
- `409`: misma secuencia con payload diferente, sin sobrescribir el original;
- `401`: autenticación inválida, credencial revocada o dispositivo inactivo;
- `403`: credencial válida para otra identidad.

## Modelo relacional

```mermaid
erDiagram
  IOT_GROUPS ||--o{ DEVICES : contiene
  DEVICES ||--o{ SENSORS : instala
  SENSOR_TYPES ||--o{ SENSORS : clasifica
  SENSORS ||--o{ CALIBRATIONS : calibra
  DEVICES ||--o{ DEVICE_CREDENTIALS : autoriza
  DEVICES ||--o{ TELEMETRY_SAMPLES : genera
  DEVICE_CREDENTIALS o|--o{ TELEMETRY_SAMPLES : atribuye
  TELEMETRY_SAMPLES ||--o{ SENSOR_MEASUREMENTS : agrupa
  SENSORS ||--o{ SENSOR_MEASUREMENTS : produce
  CALIBRATIONS o|--o{ SENSOR_MEASUREMENTS : aplica
  TELEMETRY_SAMPLES ||--o{ SAMPLE_QUALITY_FLAGS : presenta
  QUALITY_FLAG_TYPES ||--o{ SAMPLE_QUALITY_FLAGS : clasifica
```

El esquema final contiene **12 tablas físicas**, **12 claves foráneas documentadas** y **10 tablas relacionadas**: organización, inventario, telemetría, calidad y seguridad. `legacy_records` conserva compatibilidad v1 y `schema_migrations` controla `001_initial`, `002_device_credentials` y `003_postgresql_portability`. `sensor_measurements` es una tabla indexada en Supabase y una hypertable en instalaciones con TimescaleDB.

`telemetry_samples` conserva:

- referencia opcional a la credencial de ingesta;
- snapshot del alias del dispositivo;
- snapshot del alias de la credencial;
- fingerprint SHA-256 del payload.

Así, renombrar o revocar después no borra la atribución histórica.

## Consultas y Power BI

- `vw_telemetry_wide`: una fila por muestra con ambas variables, estados, flags, alias histórico, autor de inserción, credencial y fingerprint.
- `vw_powerbi_daily_summary`: resumen diario por grupo/dispositivo para KPIs.
- La API comparte filtros por grupo, dispositivo, fechas, variable y rango entre consulta y exportación.

## Frontend

`streamlit_app.py` registra cinco páginas:

- `catalog.py`: monitoreo, filtros, tiempo real y exportación;
- `register.py`: simulador de ingesta autenticada;
- `admin.py`: dispositivos y credenciales;
- `analytics.py`: limpieza, EDA, correlación e IQR;
- `models.py`: persistencia, regresión lineal y k-NN.

`api_client.py` centraliza operaciones públicas, headers de dispositivo y headers administrativos. `realtime.py` escucha WebSocket e invalida caché para consultar nuevamente la API.

## Límites conocidos

- Las rutas de lectura, exportación y WebSocket no requieren autenticación en la versión actual.
- El transporte local es HTTP; producción requiere HTTPS, proxy inverso, secretos externos y rate limiting.
- WebSocket está en memoria y requiere un broker para varias réplicas.
- Las credenciales bootstrap no sustituyen cuentas humanas, roles ni auditoría de administradores.
- Los porcentajes dependen de calibración física real.
- Los modelos son demostrativos y requieren más datos para decisiones agronómicas.
- Power BI Desktop no está disponible en macOS; el `.pbix` debe ensamblarse en Windows con `powerbi/README.md`.
