# Guía de alojamiento cloud y conexión con Power BI

## 1. Recomendación para este proyecto

La migración funciona en dos modos: PostgreSQL 17 estándar en Supabase y TimescaleDB cuando la extensión está disponible. Para el despliegue actual se recomienda:

| Componente | Servicio recomendado | Motivo |
|---|---|---|
| PostgreSQL | **Supabase PostgreSQL 17** | Servicio ya elegido, endpoint TLS y compatibilidad con el esquema portable |
| API FastAPI | **Render Web Service** | Despliegue desde Dockerfile, HTTPS administrado, healthchecks y WebSocket |
| Frontend Streamlit | **Render Web Service** | Puede usar el Dockerfile actual y conectarse a la API mediante HTTPS/WSS |
| Informes | **Power BI Desktop/Service** | Conector PostgreSQL nativo, Import o DirectQuery y soporte de gateway |

Arquitectura recomendada:

```mermaid
flowchart LR
    ESP[ESP32] -->|HTTPS + API key/secret| API[FastAPI en Render]
    WEB[Usuario] -->|HTTPS| ST[Streamlit en Render]
    ST -->|HTTPS + WSS| API
    API -->|PostgreSQL + TLS| DB[(Supabase PostgreSQL 17)]
    PBI[Power BI Desktop o Service] -->|PostgreSQL + TLS<br/>rol de solo lectura| DB
```

Power BI debe conectarse **directamente a PostgreSQL**, no a FastAPI. Debe leer estas vistas:

- `vw_telemetry_wide`: detalle de cada muestra;
- `vw_powerbi_daily_summary`: resumen diario para indicadores.

> La recomendación supone una entrega académica o un despliegue pequeño. La API debe mantenerse en **una réplica** mientras el hub WebSocket continúe en memoria.

## 2. Comparación de proveedores

### 2.1 Base de datos

| Alternativa | Compatibilidad | Ventajas | Consideraciones | Recomendación |
|---|---|---|---|---|
| **Supabase PostgreSQL 17** | PostgreSQL estándar | TLS, backups, panel y servicio ya elegido | No ofrece TimescaleDB; la migración usa la tabla estándar indexada | **Primera opción actual** |
| **Tiger Cloud** | Nativa para PostgreSQL/TimescaleDB | Operación especializada en series temporales | Servicio adicional y costos/límites propios | Si se exige TimescaleDB en cloud |
| **Aiven for PostgreSQL** | TimescaleDB según servicio | PostgreSQL administrado y extensión habilitable | Verificar versión y funciones disponibles | Alternativa con TimescaleDB |
| **Azure Database for PostgreSQL** | PostgreSQL; extensiones según versión/región | Integración favorable con Power BI y red privada | Confirmar extensiones requeridas antes de contratar | Opción empresarial |
| **VPS** | Completa usando la imagen Docker actual | Control total y posibilidad de ejecutar todo el Compose | El equipo administra TLS, firewall, backups, parches y monitoreo | Si sabes operar Linux |

Supabase PostgreSQL 17 no incluye TimescaleDB. La migración detecta esta situación y conserva `sensor_measurements` como tabla PostgreSQL estándar indexada; la vista diaria usa `date_trunc` con límites UTC, por lo que API, Streamlit y Power BI mantienen el mismo contrato independientemente de la zona de sesión. Consulta la [documentación de TimescaleDB en Supabase](https://supabase.com/docs/guides/database/extensions/timescaledb) y su [guía de migración a PostgreSQL particionado](https://supabase.com/docs/guides/database/migrating-to-pg-partman) si el volumen futuro exige particionamiento.

Tiger Cloud sigue siendo una alternativa si la entrega debe demostrar una hypertable en cloud: [conexión con psql](https://docs.tigerdata.com/integrations/latest/psql) y [creación de servicios](https://docs.tigerdata.com/getting-started/latest/services/).

### 2.2 API y frontend

| Alternativa | Docker | WebSocket | Operación | Uso sugerido |
|---|---:|---:|---|---|
| **Render** | Sí | Sí | HTTPS, dominios y healthchecks administrados | **Primera opción** para API y Streamlit |
| **Railway** | Sí | Adecuado para servicios HTTP persistentes | Despliegue y healthchecks sencillos; cobro por plan/consumo | Alternativa simple |
| **Fly.io** | Sí | Sí | Más control de red y regiones, pero requiere más configuración | Si necesitas cercanía geográfica |
| **DigitalOcean App Platform** | Sí | Sí para aplicaciones web | Plataforma administrada con healthchecks | Alternativa a Render |
| **VPS único** | Docker Compose completo | Sí, detrás de proxy | Máximo control y máxima responsabilidad | Laboratorio o equipo con experiencia Linux |

Render permite desplegar servicios web desde repositorios o imágenes Docker, configurar el puerto esperado y usar TLS administrado: [Web Services](https://render.com/docs/web-services). También soporta conexiones WebSocket públicas: [WebSockets on Render](https://render.com/docs/websocket).

Railway construye desde Dockerfile y puede esperar un healthcheck antes de declarar activo un despliegue: [Deployments reference](https://docs.railway.com/deployments/reference) y [Healthchecks](https://docs.railway.com/guides/healthchecks-and-restarts).

## 3. Preparación antes de desplegar

1. Sube el proyecto a un repositorio Git privado o público.
2. Confirma que `.env`, claves WiFi, credenciales de dispositivos y certificados no estén versionados.
3. Genera secretos distintos a los defaults:

```bash
openssl rand -hex 32  # CREDENTIAL_PEPPER
openssl rand -hex 24  # ADMIN_API_KEY
openssl rand -hex 32  # ADMIN_SECRET_KEY
```

4. Conserva `CREDENTIAL_PEPPER` en el gestor de secretos y en un respaldo seguro. Si cambia, las API keys emitidas dejan de poder localizarse.
5. Decide la región. Base, API y frontend deberían estar en regiones cercanas para reducir latencia.
6. Instala `psql` en el equipo desde el que ejecutarás las migraciones. En macOS puede instalarse con:

```bash
brew install libpq
brew link --force libpq
```

7. No publiques todavía credenciales de firmware. Primero despliega y valida la API HTTPS.

## 4. Preparar Supabase PostgreSQL 17

### 4.1 Obtener una conexión segura

1. Rota cualquier contraseña que haya sido compartida en chats, capturas o archivos.
2. En **Connect** copia la conexión directa; si tu red no admite IPv6, usa el pooler en modo sesión para la API.
3. Guarda en un gestor de secretos:
   - host;
   - puerto;
   - base de datos;
   - usuario;
   - contraseña;
   - URI/DSN con TLS.
4. No pegues estos valores en documentación, Git, capturas o tickets.

Ejemplo con valores ficticios:

```text
postgresql://USUARIO:CONTRASENA@HOST:PUERTO/BASE?sslmode=require
```

La contraseña debe codificarse como componente URI si contiene caracteres reservados.

### 4.2 Ejecutar las migraciones

Desde la raíz del repositorio:

```bash
export DATABASE_URL='postgresql://USUARIO:CONTRASENA@HOST:PUERTO/BASE?sslmode=require'

for file in backend/migrations/*.sql; do
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$file"
done
```

Los archivos deben ejecutarse con `psql` porque usan `\set`, `\gset` y `\if`. No los pegues en una herramienta que ignore metacomandos de `psql`.

Comprueba el resultado:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 <<'SQL'
SELECT version, applied_at
FROM schema_migrations
ORDER BY version;

SELECT EXISTS (
    SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'
) AS timescaledb_enabled;

SELECT COUNT(*) AS public_tables
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_type = 'BASE TABLE';

SELECT table_name
FROM information_schema.views
WHERE table_schema = 'public'
  AND table_name IN ('vw_telemetry_wide', 'vw_powerbi_daily_summary')
ORDER BY table_name;
SQL
```

Resultado esperado en Supabase PostgreSQL 17:

- migraciones `001_initial`, `002_device_credentials` y `003_postgresql_portability`;
- `timescaledb_enabled = false` y `sensor_measurements` como tabla estándar;
- 12 tablas físicas;
- vistas `vw_telemetry_wide` y `vw_powerbi_daily_summary`.

### 4.3 Crear un usuario de ejecución para la API

No uses permanentemente el propietario de migraciones en FastAPI. Conéctate como propietario y adapta los placeholders:

```sql
CREATE ROLE agro_api LOGIN PASSWORD 'CONTRASENA-ALEATORIA-API';
GRANT CONNECT ON DATABASE NOMBRE_REAL_BASE TO agro_api;
GRANT USAGE ON SCHEMA public TO agro_api;

GRANT SELECT ON
    schema_migrations, iot_groups, devices, sensor_types, sensors,
    calibrations, device_credentials, telemetry_samples, legacy_records,
    vw_telemetry_wide
TO agro_api;

GRANT INSERT ON
    iot_groups, devices, sensors, calibrations, device_credentials,
    telemetry_samples, sensor_measurements, sample_quality_flags,
    legacy_records
TO agro_api;

GRANT UPDATE ON iot_groups, devices, device_credentials TO agro_api;
```

Estos permisos corresponden a los repositorios actuales: la API no necesita `DELETE` ni modificar catálogos, migraciones o muestras históricas. Después crea el `DATABASE_URL` con `agro_api`, no con el propietario, y prueba que la API pueda arrancar y responder `/health/ready`. Si agregas futuras migraciones u operaciones, revisa y renueva los permisos de los objetos nuevos.

## 5. Desplegar FastAPI en Render

Crea un **Web Service** conectado al repositorio.

Configuración sugerida:

| Campo | Valor |
|---|---|
| Runtime | Docker |
| Dockerfile | `backend/Dockerfile` |
| Docker build context | raíz del repositorio |
| Puerto esperado | `8000` |
| Health check | `/health/ready` |
| Réplicas | `1` |
| Región | cercana a la base |

El Dockerfile actual escucha en `0.0.0.0:8000`. En Render configura `PORT=8000`; aunque el proceso no lee esa variable, informa a la plataforma del puerto utilizado.

Variables y secretos de la API:

```dotenv
DATABASE_URL=postgresql://agro_api:CONTRASENA@HOST:PUERTO/BASE?sslmode=require
DATABASE_POOL_MIN_SIZE=1
DATABASE_POOL_MAX_SIZE=5
CORS_ORIGINS=https://URL-REAL-DEL-FRONTEND
MAX_TELEMETRY_BODY_BYTES=65536
MAX_LEGACY_BODY_BYTES=1048576
CREDENTIAL_PEPPER=<PEGAR_EL_HEX_DE_64_CARACTERES_GENERADO>
ADMIN_API_KEY=<PEGAR_UN_VALOR_DE_AL_MENOS_16_CARACTERES>
ADMIN_SECRET_KEY=<PEGAR_UN_VALOR_DE_AL_MENOS_24_CARACTERES>
PORT=8000
```

No definas `POSTGRES_PASSWORD`, `POSTGRES_PORT` ni el servicio `postgres` del Compose en Render: la base ya está administrada externamente.

Después del despliegue:

```bash
curl -i https://URL-API/health/live
curl -i https://URL-API/health/ready
```

`/health/ready` debe responder `200` y mostrar PostgreSQL conectado. Al arrancar, el proceso verifica las tablas y la migración `003_postgresql_portability`; TimescaleDB no es obligatorio en Supabase. Cada llamada posterior a readiness comprueba la conexión con PostgreSQL, no repite toda la auditoría del esquema.

También verifica WebSocket con un cliente compatible:

```text
wss://URL-API/api/v2/telemetry/events
```

Mantén una sola réplica. El hub de eventos está en memoria y varias réplicas pueden provocar que un POST y un cliente WebSocket lleguen a procesos distintos. Para escalar horizontalmente primero incorpora Redis Pub/Sub, Streams o un outbox compartido.

## 6. Desplegar Streamlit en Render

Crea un segundo **Web Service** desde el mismo repositorio.

| Campo | Valor |
|---|---|
| Runtime | Docker |
| Dockerfile | `frontend/Dockerfile` |
| Docker build context | raíz del repositorio |
| Puerto esperado | `8501` |
| Health check | `/_stcore/health` |

Variables:

```dotenv
API_BASE_URL=https://URL-API
PORT=8501
```

El Dockerfile de Streamlit escucha explícitamente en `0.0.0.0:8501`; igual que en la API, `PORT=8501` informa a Render del puerto, pero el proceso actual no lee esa variable.

El frontend convertirá automáticamente:

```text
https://URL-API → wss://URL-API/api/v2/telemetry/events
```

Cuando Render entregue la URL definitiva del frontend, vuelve a la API y configura:

```dotenv
CORS_ORIGINS=https://URL-REAL-DEL-FRONTEND
```

Luego valida:

```bash
curl -i https://URL-FRONTEND/_stcore/health
```

Prueba las cinco páginas: Monitoreo, Simulador, Administración, Análisis exploratorio y Modelos predictivos.

## 7. Configurar el ESP32 para cloud

1. Registra el dispositivo desde Administración.
2. Emite una credencial específica para ese ESP32.
3. Cambia en el firmware:

```cpp
const char* API_URL = "https://URL-API/api/v2/telemetry/samples";
const char* GROUP_ID = "grupo-01";
const char* DEVICE_ID = "esp32-grupo-01";
const char* API_KEY = "API_KEY_EMITIDA";
const char* SECRET_KEY = "SECRET_EMITIDA";
```

4. Valida el certificado TLS con `WiFiClientSecure` y una CA confiable. Cambiar únicamente `http://` por `https://` sin validar el certificado no protege contra suplantación.
5. Prueba primero una muestra y confirma `201`; repite exactamente el payload y confirma `200` idempotente.
6. No publiques el sketch con credenciales reales. Para instalación permanente, carga secretos desde un mecanismo de aprovisionamiento o almacenamiento protegido.

## 8. Crear el usuario de Power BI

Power BI nunca debe usar el usuario propietario ni `agro_api`. Parte de `powerbi/CREAR_ROL_LECTURA.sql` y cambia:

- `CAMBIAR-CONTRASENA-FUERTE` por una contraseña aleatoria;
- `agro_iot` por el nombre real de la base cloud, si es distinto.

La intención del script es:

```sql
CREATE ROLE powerbi_reader LOGIN PASSWORD 'CONTRASENA-ALEATORIA';
GRANT CONNECT ON DATABASE NOMBRE_REAL_BASE TO powerbi_reader;
GRANT USAGE ON SCHEMA public TO powerbi_reader;
GRANT SELECT ON vw_telemetry_wide, vw_powerbi_daily_summary TO powerbi_reader;
```

Comprueba el mínimo privilegio conectándote como `powerbi_reader`:

```sql
SELECT COUNT(*) FROM vw_telemetry_wide;          -- debe funcionar
SELECT COUNT(*) FROM vw_powerbi_daily_summary;   -- debe funcionar
SELECT * FROM device_credentials;                -- debe fallar
```

## 9. Conectar Power BI Desktop

Microsoft documenta que el conector PostgreSQL soporta **Import** y **DirectQuery**, además de conexiones cloud y gateways: [PostgreSQL connector](https://learn.microsoft.com/power-query/connectors/postgresql).

Power BI Desktop requiere Windows. En un equipo Windows:

1. Abre Power BI Desktop.
2. Selecciona **Obtener datos → PostgreSQL database**.
3. En **Servidor**, escribe:

```text
HOST:PUERTO
```

4. En **Base de datos**, escribe el nombre real de la base cloud.
5. Elige el modo:
   - **Import**, recomendado para este proyecto académico: carga más rápido los gráficos y reduce consultas a la base;
   - **DirectQuery**, si necesitas consultar el estado actual en cada interacción o si el docente lo exige.
6. Selecciona autenticación de base de datos.
7. Usuario: `powerbi_reader`.
8. Introduce la contraseña de ese rol.
9. Mantén la conexión cifrada. No aceptes conexión sin cifrado.
10. En el navegador selecciona:
    - `public.vw_telemetry_wide`;
    - `public.vw_powerbi_daily_summary`.
11. Pulsa **Transformar datos** para revisar tipos antes de cargar.

Tipos recomendados:

| Campo | Tipo Power BI |
|---|---|
| `measured_at`, `received_at`, `day` | Fecha/Hora con zona o Fecha/Hora |
| porcentajes | Número decimal |
| ADC, secuencia y conteos | Número entero |
| `rain_detected` | Verdadero/Falso |
| IDs, aliases, estados | Texto |

No relaciones directamente detalle y resumen diario si eso produce doble conteo. Puedes usar la vista detallada para tendencias y la diaria en una página de KPIs, o construir dimensiones separadas de fecha/dispositivo.

Las medidas están en `powerbi/MEDIDAS_DAX.md` y la composición mínima en `powerbi/README.md`.

### Import frente a DirectQuery

| Criterio | Import | DirectQuery |
|---|---|---|
| Rendimiento del informe | Generalmente mejor | Depende de red y base |
| Actualidad | Al último refresh | Consulta al interactuar |
| Carga sobre PostgreSQL | Durante refresh | En cada visual/filtro |
| Trabajo sin conexión | Parcialmente posible | No |
| Recomendación inicial | **Sí** | Solo si es requisito |

DirectQuery no importa los datos al modelo y consulta el origen durante el uso; Microsoft detalla sus implicaciones en [DirectQuery in Power BI](https://learn.microsoft.com/power-bi/connect-data/desktop-directquery-about).

## 10. Publicar en Power BI Service

### Caso A: base cloud alcanzable públicamente y protegida

1. Publica el `.pbix` desde Power BI Desktop.
2. En Power BI Service abre la configuración del modelo semántico.
3. Crea o selecciona una **cloud connection** PostgreSQL.
4. Usa el mismo host, base y `powerbi_reader`.
5. Exige conexión cifrada.
6. Si usaste Import, configura actualización programada.
7. Ejecuta **Refresh now** y confirma la fecha de actualización.

Power BI permite compartir conexiones cloud para modelos y otros artefactos: [conexiones a fuentes cloud](https://learn.microsoft.com/power-bi/connect-data/service-connect-cloud-data-sources).

### Caso B: base privada, VPN o allowlist que no admite Power BI Service

Instala un **On-premises data gateway** en una máquina Windows de 64 bits que:

- permanezca encendida durante consultas/actualizaciones;
- pueda resolver el DNS y alcanzar el host PostgreSQL;
- use el rol `powerbi_reader`;
- tenga salida hacia Power BI Service.

También puede usarse un gateway de red virtual en arquitecturas Azure compatibles. Desde junio de 2025, Microsoft indica que el gateway incluye el proveedor Npgsql requerido por PostgreSQL; usa siempre una versión actual del gateway.

## 11. Red y seguridad obligatoria

### Base de datos

- TLS obligatorio para API y Power BI.
- No habilites acceso universal `0.0.0.0/0` de forma permanente.
- Permite únicamente IPs/rangos necesarios o usa red privada + gateway.
- Usa usuarios distintos: propietario/migración, `agro_api` y `powerbi_reader`.
- Habilita backups automáticos y prueba una restauración.
- Supervisa almacenamiento, conexiones y consultas lentas.

### API y frontend

- Mantén secretos exclusivamente en el gestor del proveedor.
- Usa HTTPS/WSS; Render termina TLS para los servicios web.
- Configura límites de gasto y alertas del proveedor.
- Mantén `CORS_ORIGINS` limitado al frontend real.
- Añade rate limiting en el proxy o gateway.
- Protege logs y evita registrar headers de autenticación.

### Limitación actual importante

La ingesta v2 y la administración están autenticadas, pero actualmente son públicos:

- las consultas GET v1 y v2;
- las exportaciones v1 y v2;
- los WebSocket v1 y v2;
- `POST /api/v1/records`, que todavía permite escribir objetos JSONB por compatibilidad.

Antes de exponer datos sensibles, añade autenticación de lectura y protege o deshabilita la API v1, o coloca un gateway/proxy que controle esas rutas. CORS no es un control de acceso. Para una demostración académica, limita temporalmente el acceso por red y no uses datos personales o sensibles.

## 12. Comprobación integral después del despliegue

### API y frontend

```bash
curl -f https://URL-API/health/live
curl -f https://URL-API/health/ready
curl -f https://URL-FRONTEND/_stcore/health
```

### Base de datos

```sql
SELECT version FROM schema_migrations ORDER BY version;

SELECT to_regclass('public.sensor_measurements') AS measurements_table;

SELECT EXISTS (
    SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'
) AS timescaledb_enabled;

SELECT COUNT(*), MAX(measured_at)
FROM vw_telemetry_wide;
```

### Power BI

1. Inserta una muestra nueva desde el ESP32 o Simulador.
2. Confirma que aparece en Streamlit.
3. En Import pulsa **Actualizar**; en DirectQuery interactúa con un filtro.
4. Comprueba la muestra en `vw_telemetry_wide`.
5. Cambia fecha, dispositivo y grupo en los segmentadores.
6. Verifica que el origen sea PostgreSQL, no CSV o Excel.
7. Guarda, cierra y vuelve a abrir el `.pbix`.

## 13. Cuándo elegir otra arquitectura

- **Railway + Tiger Cloud:** si prefieres una interfaz de despliegue y consumo simple.
- **Aiven + Render:** si deseas PostgreSQL administrado general con TimescaleDB ApacheOnly y las funciones usadas siguen disponibles.
- **Azure Database for PostgreSQL + Azure Container Apps:** si Power BI Service, redes privadas y gobierno Azure son prioritarios; verifica primero la versión exacta de TimescaleDB.
- **VPS único:** si el presupuesto es el factor principal y puedes administrar Caddy/Nginx, certificados, firewall, backups y actualizaciones.
- **Varias réplicas de API:** solo después de sustituir el hub WebSocket en memoria por un canal compartido.

## 14. Checklist de decisión

Antes de publicar, confirma:

- [ ] El endpoint PostgreSQL admite TLS y Power BI puede alcanzarlo.
- [ ] La migración produce 12 tablas y las dos vistas.
- [ ] `schema_migrations` contiene `001_initial`, `002_device_credentials` y `003_postgresql_portability`.
- [ ] Existen backups y restauración.
- [ ] API y frontend pueden ejecutar Dockerfiles distintos desde el mismo repo.
- [ ] El host soporta WebSocket/WSS.
- [ ] Se pueden configurar healthchecks y secretos.
- [ ] El costo de servicio siempre activo cabe en el presupuesto.
- [ ] La región y latencia son aceptables para el ESP32.
- [ ] Si la evaluación exige TimescaleDB literalmente, existe evidencia del entorno Docker local o de un proveedor compatible.

## Fuentes oficiales

- [Supabase: TimescaleDB](https://supabase.com/docs/guides/database/extensions/timescaledb)
- [Supabase: migrar de TimescaleDB a pg_partman](https://supabase.com/docs/guides/database/migrating-to-pg-partman)

- [Tiger Cloud: crear servicio](https://docs.tigerdata.com/getting-started/latest/services/)
- [Tiger Cloud: conexión PostgreSQL con psql](https://docs.tigerdata.com/integrations/latest/psql)
- [Aiven: TimescaleDB en PostgreSQL](https://aiven.io/docs/products/postgresql/concepts/timescaledb)
- [Render: Web Services y Docker](https://render.com/docs/web-services)
- [Render: WebSocket](https://render.com/docs/websocket)
- [Railway: referencia de despliegues](https://docs.railway.com/deployments/reference)
- [Railway: healthchecks](https://docs.railway.com/guides/healthchecks-and-restarts)
- [Microsoft: conector PostgreSQL de Power Query/Power BI](https://learn.microsoft.com/power-query/connectors/postgresql)
- [Microsoft: fuentes cloud en Power BI Service](https://learn.microsoft.com/power-bi/connect-data/service-connect-cloud-data-sources)
- [Microsoft: DirectQuery](https://learn.microsoft.com/power-bi/connect-data/desktop-directquery-about)

> Contenido de fuentes web parafraseado para cumplir restricciones de licencia. Los precios, planes gratuitos, regiones y límites cambian; compruébalos en las páginas oficiales antes de contratar.
