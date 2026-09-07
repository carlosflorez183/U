# Firmware ESP32 agrícola

Este sketch captura humedad del suelo y lluvia, muestra el estado en LCD y envía JSON autenticado a `POST /api/v2/telemetry/samples`.

## Bibliotecas

Instala desde Arduino Library Manager:

- ArduinoJson.
- LiquidCrystal I2C.

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
   - calibración seca/húmeda de ambos sensores.

El POST añade estos headers:

```http
Content-Type: application/json
X-API-Key: ak_...
X-Secret-Key: sk_...
```

No guarde credenciales reales en Git, capturas o documentación. En producción use HTTPS: con HTTP los headers pueden observarse en la red. Para un montaje permanente es preferible provisionar las claves en NVS en vez de dejarlas en el sketch.

## Respuestas

El firmware no envía `sequence`: la API la asigna de forma atómica por dispositivo y la incluye en la respuesta.

- `201`: muestra nueva con secuencia asignada por el backend.
- `200`: reintento con exactamente el mismo payload; devuelve la muestra y secuencia originales.
- `401`: clave ausente, incorrecta, revocada o dispositivo inactivo.
- `403`: la credencial pertenece a otro grupo/dispositivo.

Una credencial revocada debe sustituirse desde Administración. Si se implementan reintentos automáticos en el firmware, deben reutilizar exactamente el mismo JSON —incluido `measured_at`— hasta recibir `200` o `201`.

Consulta `../../docs/CIRCUITO_ESP32.md` antes de energizar el montaje. Antes de la sustentación verifique físicamente LCD, cable UTP, alimentación y calibración seca/húmeda.
