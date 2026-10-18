/*
 * ESP32: DHT22 + LCD I2C + teclado matricial 4x4 (Taller 1, Corte 2).
 *
 * Único sensor: DHT22 (AM2302). Mide temperatura y humedad relativa del aire.
 * Cada 20 s envía la lectura a la API en la nube (Render) y, con el teclado,
 * consulta siete analíticas que se muestran en el LCD:
 *   1 tiempo real | 2 promedio hora | 3 max/min dia | 4 desviacion y tendencia
 *   5 atipicos    | 6 alertas       | 7 estado de la nube
 *   * vuelve a la pantalla en vivo  # actualiza la opcion seleccionada
 *
 * Si la nube no responde, las lecturas se guardan en un búfer en RAM (32
 * posiciones) y se reintentan cada 15 s sin perder la fecha original.
 *
 * Antes de cargar:
 * 1. Registra el dispositivo y genera una credencial desde Administración.
 * 2. Configura WIFI, API_HOST, GROUP_ID, DEVICE_ID, API_KEY y SECRET_KEY.
 * 3. Conecta el DHT22 a DHT_DATA_PIN con pull-up de 10 kΩ a 3V3.
 * 4. Conecta el LCD I2C a SDA=21, SCL=22, VCC=3V3, GND.
 * 5. Conecta el teclado 4x4: filas 32/33/25/26, columnas 27/14/12/13.
 * 6. Instala ArduinoJson, LiquidCrystal_I2C y DHT sensor library.
 */

#include <Arduino.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <HTTPClient.h>
#include <LiquidCrystal_I2C.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <Wire.h>
#include <time.h>

const char* WIFI_SSID = "CAMBIAR_SSID";
const char* WIFI_PASSWORD = "CAMBIAR_PASSWORD";
// Sin barra final: ej. https://api-estacion-climatica.onrender.com o http://IP:18000
const char* API_HOST = "CAMBIAR_API_HOST";
const char* GROUP_ID = "grupo-01";
const char* DEVICE_ID = "esp32-grupo-01";
// Valores emitidos una sola vez por POST /api/v2/admin/credentials.
// No confirmes este archivo con credenciales reales en control de versiones.
const char* API_KEY = "CAMBIAR_API_KEY";
const char* SECRET_KEY = "CAMBIAR_SECRET_KEY";

constexpr uint8_t DHT_DATA_PIN = 4;  // Digital; pull-up de 10 kΩ a 3V3.
constexpr uint8_t I2C_SDA_PIN = 21;
constexpr uint8_t I2C_SCL_PIN = 22;
constexpr uint32_t SAMPLE_PERIOD_MS = 20000;  // Una lectura cada 20 segundos.
constexpr uint32_t RETRY_PERIOD_MS = 15000;
constexpr uint8_t PENDING_CAPACITY = 32;

// Teclado matricial 4x4.
const uint8_t ROW_PINS[4] = {32, 33, 25, 26};
const uint8_t COL_PINS[4] = {27, 14, 12, 13};
const char KEYS[4][4] = {
  {'1', '2', '3', 'A'},
  {'4', '5', '6', 'B'},
  {'7', '8', '9', 'C'},
  {'*', '0', '#', 'D'},
};

// Rango físico declarado por la hoja de datos del DHT22 (AM2302).
constexpr float DHT_MIN_TEMPERATURE_C = -40.0f;
constexpr float DHT_MAX_TEMPERATURE_C = 80.0f;
constexpr float DHT_MIN_HUMIDITY_PERCENT = 0.0f;
constexpr float DHT_MAX_HUMIDITY_PERCENT = 100.0f;

LiquidCrystal_I2C lcd(0x27, 16, 2);
DHT dht(DHT_DATA_PIN, DHT22);

struct PendingSample {
  char measuredAt[25];
  float temperature;
  float humidity;
};

PendingSample pending[PENDING_CAPACITY];
uint8_t pendingCount = 0;
unsigned long lastSampleAt = 0;
unsigned long lastFlushAt = 0;
bool menuActive = false;
uint8_t menuOption = 0;

float roundToTenth(float value) {
  return round(value * 10.0f) / 10.0f;
}

bool readAmbient(float& temperatureC, float& humidityPercent) {
  // Dos intentos: el DHT22 falla ocasionalmente por temporización del bus.
  for (int attempt = 0; attempt < 2; ++attempt) {
    if (attempt > 0) delay(2100);
    humidityPercent = dht.readHumidity();
    temperatureC = dht.readTemperature();
    if (isnan(humidityPercent) || isnan(temperatureC)) continue;
    if (temperatureC < DHT_MIN_TEMPERATURE_C || temperatureC > DHT_MAX_TEMPERATURE_C) {
      continue;
    }
    if (humidityPercent < DHT_MIN_HUMIDITY_PERCENT ||
        humidityPercent > DHT_MAX_HUMIDITY_PERCENT) {
      continue;
    }
    return true;
  }
  return false;
}

String iso8601Now() {
  struct tm timeInfo;
  if (!getLocalTime(&timeInfo, 2000)) return "";
  char buffer[25];
  strftime(buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%SZ", &timeInfo);
  return String(buffer);
}

String shortTime(const String& iso) {
  if (iso.length() < 19) return iso;
  return iso.substring(11, 19);
}

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  lcd.clear();
  lcd.print("Conectando WiFi");
  for (int attempt = 0; attempt < 30 && WiFi.status() != WL_CONNECTED; ++attempt) {
    delay(500);
  }
}

void showLiveData(float temperature = NAN, float humidity = NAN) {
  menuActive = false;
  lcd.clear();
  if (isnan(temperature) || isnan(humidity)) {
    lcd.setCursor(0, 0);
    lcd.print("Estacion IoT");
    lcd.setCursor(0, 1);
    lcd.print("Esperando...");
    return;
  }
  lcd.setCursor(0, 0);
  lcd.printf("Temp: %5.1f C", temperature);
  lcd.setCursor(0, 1);
  lcd.printf("Hum: %5.1f %%", humidity);
}

char readKeypad() {
  for (uint8_t row = 0; row < 4; ++row) {
    pinMode(ROW_PINS[row], INPUT_PULLUP);
  }
  for (uint8_t col = 0; col < 4; ++col) {
    pinMode(COL_PINS[col], OUTPUT_OPEN_DRAIN);
    digitalWrite(COL_PINS[col], LOW);
    delay(5);
    for (uint8_t row = 0; row < 4; ++row) {
      if (digitalRead(ROW_PINS[row]) == LOW) {
        while (digitalRead(ROW_PINS[row]) == LOW) delay(10);  // antirrebote
        pinMode(COL_PINS[col], INPUT_PULLUP);
        return KEYS[row][col];
      }
    }
    pinMode(COL_PINS[col], INPUT_PULLUP);
  }
  return 0;
}

int httpJson(const char* url, const char* body, String* responseBody,
             const char* method = "POST") {
  connectWiFi();
  if (WiFi.status() != WL_CONNECTED) return -1;
  HTTPClient http;
  WiFiClientSecure secureClient;
  http.setConnectTimeout(5000);
  http.setTimeout(5000);
  if (strncmp(url, "https://", 8) == 0) {
    secureClient.setInsecure();  // Demo: sin validar el certificado de Render.
    http.begin(secureClient, url);
  } else {
    http.begin(url);
  }
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", API_KEY);
  http.addHeader("X-Secret-Key", SECRET_KEY);
  int code = (strcmp(method, "GET") == 0) ? http.GET() : http.POST(body);
  if (responseBody != nullptr && code > 0) {
    *responseBody = http.getString();
  }
  http.end();
  return code;
}

void enqueuePending(const char* measuredAt, float temperature, float humidity) {
  if (pendingCount >= PENDING_CAPACITY) {
    memmove(&pending[0], &pending[1], sizeof(PendingSample) * (PENDING_CAPACITY - 1));
    pendingCount = PENDING_CAPACITY - 1;
  }
  strlcpy(pending[pendingCount].measuredAt, measuredAt, sizeof(pending[0].measuredAt));
  pending[pendingCount].temperature = temperature;
  pending[pendingCount].humidity = humidity;
  ++pendingCount;
}

int postSample(const char* measuredAt, float temperature, float humidity) {
  JsonDocument document;
  document["schema_version"] = "2.0";
  document["group_id"] = GROUP_ID;
  document["device_id"] = DEVICE_ID;
  document["measured_at"] = measuredAt;
  document["sampling_period_seconds"] = SAMPLE_PERIOD_MS / 1000;
  document["ambient"]["temperature_celsius"] = roundToTenth(temperature);
  document["ambient"]["humidity_percent"] = roundToTenth(humidity);
  String body;
  serializeJson(document, body);
  String url = String(API_HOST) + "/api/v2/telemetry/samples";
  String ignored;
  return httpJson(url.c_str(), body.c_str(), &ignored);
}

void flushPending() {
  while (pendingCount > 0) {
    int code = postSample(pending[0].measuredAt, pending[0].temperature,
                          pending[0].humidity);
    if (code != 201 && code != 200) return;
    memmove(&pending[0], &pending[1], sizeof(PendingSample) * pendingCount);
    --pendingCount;
  }
}

String menuUrl(uint8_t option) {
  const char* paths[] = {
      "", "realtime", "hourly-average", "daily-extremes",
      "trend", "outliers", "alerts", "connection"};
  return String(API_HOST) + "/api/v2/menu/" + paths[option];
}

void showMenuResult(uint8_t option) {
  String body;
  String url = menuUrl(option);
  int code = httpJson(url.c_str(), nullptr, &body, "GET");
  lcd.clear();
  if (code != 200) {
    lcd.setCursor(0, 0);
    lcd.printf("Opcion %u", option);
    lcd.setCursor(0, 1);
    lcd.print("Sin conexion");
    return;
  }
  JsonDocument doc;
  if (deserializeJson(doc, body) != DeserializationError::Ok) {
    lcd.setCursor(0, 1);
    lcd.print("Respuesta inv.");
    return;
  }
  lcd.setCursor(0, 0);
  lcd.printf("Opcion %u", option);
  lcd.setCursor(0, 1);
  switch (option) {
    case 1: {
      if (doc["temperature_celsius"].isNull()) {
        lcd.print("Sin lecturas");
        break;
      }
      lcd.printf("T:%.1fC H:%.0f%%", doc["temperature_celsius"].as<float>(),
                 doc["humidity_percent"].as<float>());
      break;
    }
    case 2:
      lcd.printf("T:%.1f H:%.1f%%", doc["avg_temperature_celsius"].as<float>(),
                 doc["avg_humidity_percent"].as<float>());
      break;
    case 3:
      lcd.printf("T %4.1f..%4.1f", doc["min_temperature_celsius"].as<float>(),
                 doc["max_temperature_celsius"].as<float>());
      break;
    case 4:
      lcd.printf("dT:%.1f dH:%.1f", doc["stddev_temperature_celsius"].as<float>(),
                 doc["stddev_humidity_percent"].as<float>());
      break;
    case 5:
      lcd.printf("Tot:%d T:%d H:%d", doc["outlier_count"].as<int>(),
                 doc["temperature_outlier_count"].as<int>(),
                 doc["humidity_outlier_count"].as<int>());
      break;
    case 6:
      lcd.printf("Tot:%d T:%d H:%d", doc["alert_count"].as<int>(),
                 doc["temperature_alert_count"].as<int>(),
                 doc["humidity_alert_count"].as<int>());
      break;
    case 7: {
      bool online = doc[0]["online"] | false;
      lcd.setCursor(0, 0);
      lcd.print(online ? "Nube: ONLINE" : "Nube: OFFLINE");
      lcd.setCursor(0, 1);
      lcd.print(shortTime(String(doc[0]["last_seen_at"] | "")));
      break;
    }
    default:
      break;
  }
}

void handleKey(char key) {
  if (key >= '1' && key <= '7') {
    menuOption = key - '0';
    menuActive = true;
    showMenuResult(menuOption);
  } else if (key == '*') {
    showLiveData();
  } else if (key == '#' && menuActive && menuOption >= 1) {
    showMenuResult(menuOption);
  }
}

void setup() {
  Serial.begin(115200);
  dht.begin();
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  lcd.init();
  lcd.backlight();
  for (uint8_t col = 0; col < 4; ++col) {
    pinMode(COL_PINS[col], INPUT_PULLUP);
  }

  connectWiFi();
  // UTC; se necesita una hora válida para measured_at.
  configTime(0, 0, "pool.ntp.org", "time.google.com");
  showLiveData();
}

void loop() {
  char key = readKeypad();
  if (key) {
    Serial.printf("tecla=%c\n", key);
    handleKey(key);
  }

  if (millis() - lastSampleAt >= SAMPLE_PERIOD_MS) {
    lastSampleAt = millis();
    float temperatureC = NAN;
    float humidityPercent = NAN;
    if (!readAmbient(temperatureC, humidityPercent)) {
      Serial.println("dht22=error");
      if (!menuActive) {
        lcd.clear();
        lcd.print("Error DHT22");
      }
      return;
    }
    if (!menuActive) showLiveData(temperatureC, humidityPercent);
    String measuredAt = iso8601Now();
    if (!measuredAt.isEmpty()) {
      int code = postSample(measuredAt.c_str(), temperatureC, humidityPercent);
      Serial.printf("temp=%.1f hum=%.1f http=%d pendientes=%d\n",
                    temperatureC, humidityPercent, code, pendingCount);
      if (code != 201 && code != 200) {
        enqueuePending(measuredAt.c_str(), temperatureC, humidityPercent);
      }
    }
  }

  if (pendingCount > 0 && millis() - lastFlushAt >= RETRY_PERIOD_MS) {
    lastFlushAt = millis();
    flushPending();
  }
}
