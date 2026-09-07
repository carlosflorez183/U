# Contrato de telemetría IoT v2

## 1. Aprovisionamiento administrativo

La ingesta no crea dispositivos automáticamente. Un administrador debe registrar el ESP32 y emitir una credencial vinculada.

Todas las rutas `/api/v2/admin/*` requieren:

```http
X-Admin-API-Key: valor-de-ADMIN_API_KEY
X-Admin-Secret-Key: valor-de-ADMIN_SECRET_KEY
```

| Método y ruta | Función |
|---|---|
| `POST /api/v2/admin/devices` | registrar dispositivo, grupo y alias |
| `GET /api/v2/admin/devices` | listar activos e inactivos |
| `POST /api/v2/admin/devices/{id}/alias` | cambiar alias actual |
| `POST /api/v2/admin/devices/{id}/activate` | activar dispositivo |
| `POST /api/v2/admin/devices/{id}/deactivate` | bloquear ingesta |
| `POST /api/v2/admin/credentials` | emitir API key/secret vinculadas |
| `GET /api/v2/admin/credentials` | listar metadata y prefijos, nunca secretos |
| `POST /api/v2/admin/credentials/{uuid}/revoke` | revocar credencial |

Registro:

```json
{
  "group_id": "grupo-01",
  "device_id": "esp32-grupo-01",
  "alias": "Sensor del invernadero norte"
}
```

Emisión de credencial:

```json
{
  "device_id": "esp32-grupo-01",
  "alias": "ESP32 operado por equipo A"
}
```

La respuesta `201` contiene `api_key` y `secret_key`. El secret se muestra una sola vez, la respuesta usa `Cache-Control: no-store` y la base solo conserva digest/hash.

## 2. Ingesta autenticada

`POST /api/v2/telemetry/samples`

Headers obligatorios:

```http
X-API-Key: ak_...
X-Secret-Key: sk_...
Content-Type: application/json
```

Cuerpo:

```json
{
  "schema_version": "2.0",
  "group_id": "grupo-01",
  "device_id": "esp32-grupo-01",
  "measured_at": "2026-09-04T14:00:00Z",
  "sampling_period_seconds": 5,
  "soil_moisture": {"raw_adc": 2470, "percent": 34.8},
  "rain": {"raw_adc": 3520, "wetness_percent": 8.1, "detected": false}
}
```

`group_id` y `device_id` deben coincidir exactamente con el dispositivo vinculado a la API key. El cliente no necesita enviar `sequence`: el backend la asigna de forma atómica. Por compatibilidad, un campo `sequence` legacy no negativo es aceptado, pero su valor se ignora.

La respuesta añade trazabilidad:

```json
{
  "device_alias": "Sensor del invernadero norte",
  "inserted_by_alias": "ESP32 operado por equipo A",
  "ingest_credential_id": "uuid-de-la-credencial",
  "duplicate": false
}
```

Los alias se guardan como snapshot: cambiar el alias actual no modifica quién aparece en muestras históricas.

## 3. Validaciones e idempotencia

- Identificadores: 2–64 caracteres alfanuméricos, `_` o `-`.
- Fecha: ISO-8601 con zona horaria.
- Periodo: 5 o 10 segundos.
- ADC: 0–4095; porcentajes: 0–100.
- Propiedades adicionales: rechazadas, salvo `sequence` legacy opcional e ignorada.
- Payload nuevo: HTTP `201`, `duplicate=false`, con `sequence` asignada por el backend.
- Mismo dispositivo y payload exacto —incluido `measured_at`—: HTTP `200`, `duplicate=true`, con la muestra original.
- Payload diferente: recibe una secuencia nueva; no colisiona con valores enviados por el dispositivo.
- Una credencial revocada falla también al reintentar un payload.

La transacción revalida credencial y dispositivo, bloquea la fila del dispositivo, detecta reintentos exactos, asigna `MAX(sequence)+1` y almacena cabecera, dos mediciones PostgreSQL, fingerprint, aliases y flags antes de publicar WebSocket.

## 4. Códigos de autenticación

| HTTP | Código | Significado |
|---:|---|---|
| 401 | `AUTHENTICATION_REQUIRED` | headers ausentes, clave incorrecta/revocada o dispositivo inactivo |
| 403 | `FORBIDDEN` | credencial válida, pero cuerpo de otro grupo/dispositivo |
| 409 | `CONFLICT` | conflicto de un recurso administrativo; la ingesta no usa la secuencia del cliente |

La respuesta no indica si falló API key o secret key, para evitar enumeración. Use `request_id` para correlacionar logs.

## 5. Consulta y exportación

Estas rutas permanecen compatibles y no requieren claves de ingesta:

```text
GET /api/v2/telemetry/samples
GET /api/v2/telemetry/devices
GET /api/v2/telemetry/groups
GET /api/v2/telemetry/export/{csv|json|xlsx|pdf}
```

Parámetros combinables: `limit`, `device_id`, `group_id`, `from`, `to`, `variable`, `min_value`, `max_value`.

## 6. Tiempo real

`ws://SERVIDOR:8000/api/v2/telemetry/events`

```json
{"type": "telemetry.sample.created", "sample": {}}
```

El evento incluye los campos de auditoría. Los reintentos idempotentes no publican un evento nuevo.

## 7. Reglas de seguridad

- Use HTTPS fuera del desarrollo local.
- Cambie `CREDENTIAL_PEPPER`, `ADMIN_API_KEY` y `ADMIN_SECRET_KEY`.
- No coloque secretos en el JSON, query string, Git o logs.
- Rote creando una credencial nueva y revocando la anterior.
- Desactivar un dispositivo bloquea todas sus credenciales sin borrarlas.
