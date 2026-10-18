# Firmware ESP32 ambiental

Este sketch captura temperatura y humedad del aire con un DHT22, muestra el estado en LCD y envía JSON autenticado a `POST /api/v2/telemetry/samples`.

## Sensor

| Sensor | Tipo | Pin | Entrega |
|---|---|---:|---|
| DHT22 (AM2302) | digital de un hilo | `4` | temperatura en °C y humedad relativa del aire |

Es el único sensor del montaje: se retiraron la humedad capacitiva del suelo y el sensor de lluvia, junto con sus pines analógicos y calibraciones.

El DHT22 no usa ADC, por lo que no produce `raw_adc`. Necesita una resistencia pull-up de 10 kΩ entre datos y 3V3, y admite como máximo una lectura cada 2 segundos. Si dos intentos consecutivos fallan o quedan fuera del rango de la hoja de datos (-40 a 80 °C y 0 a 100 %), el firmware omite el envío en lugar de inventar un valor.

## Bibliotecas

Instala desde Arduino Library Manager:

- ArduinoJson.
- LiquidCrystal I2C.
- DHT sensor library, de Adafruit, junto con Adafruit Unified Sensor.

`WiFi`, `HTTPClient`, `Wire` y `time` forman parte del core ESP32.

## Aprovisionamiento obligatorio

Antes de cargar el sketch:

1. Entre a la página **Administración** de Streamlit.
2. Registre `GROUP_ID`, `DEVICE_ID` y un alias descriptivo.
3. Emita una credencial vinculada al dispositivo y asigne un alias a quien insertará, por ejemplo `ESP32 invernadero norte`.
4. Copie inmediatamente API key y secret key; el secret no puede recuperarse.
5. Configure en `esp32_agro_iot.ino`:
   - `WIFI_SSID` y `WIFI_PASSWORD`;
   - `API_URL`, usando la IP LAN del servidor y nunca `localhost`;
   - `GROUP_ID` y `DEVICE_ID`, exactamente iguales al registro administrativo;
   - `API_KEY` y `SECRET_KEY`;
   - `DHT_DATA_PIN` si usas otro GPIO. El DHT22 llega calibrado de fábrica y no requiere ajuste manual.

El POST añade estos headers:

```http
Content-Type: application/json
X-API-Key: ak_...
X-Secret-Key: sk_...
```

No guarde credenciales reales en Git, capturas o documentación. En producción use HTTPS: con HTTP los headers pueden observarse en la red. Para un montaje permanente es preferible provisionar las claves en NVS en vez de dejarlas en el sketch.

## Payload enviado

```json
{
  "schema_version": "2.0",
  "group_id": "grupo-01",
  "device_id": "esp32-grupo-01",
  "measured_at": "2026-09-07T22:30:00Z",
  "sampling_period_seconds": 5,
  "ambient": {"temperature_celsius": 23.4, "humidity_percent": 65.2}
}
```

> **Backend actualizado:** la API v2 ya acepta `ambient` (migración `004_ambient_dht22`). Los bloques antiguos `soil_moisture`/`rain` ahora dan `422`.

## Respuestas

El firmware no envía `sequence`: la API la asigna de forma atómica por dispositivo y la incluye en la respuesta.

- `201`: muestra nueva con secuencia asignada por el backend.
- `200`: reintento con exactamente el mismo payload; devuelve la muestra y secuencia originales.
- `401`: clave ausente, incorrecta, revocada o dispositivo inactivo.
- `403`: la credencial pertenece a otro grupo/dispositivo.
- `422`: el contrato todavía espera suelo/lluvia o falta un campo requerido.

Una credencial revocada debe sustituirse desde Administración. Si se implementan reintentos automáticos en el firmware, deben reutilizar exactamente el mismo JSON —incluido `measured_at`— hasta recibir `200` o `201`.

Consulta `../../docs/CIRCUITO_ESP32.md` antes de energizar el montaje; su diagrama todavía describe suelo y lluvia. Antes de la sustentación verifica físicamente LCD, alimentación, pull-up del DHT22 y estabilidad de las lecturas.
