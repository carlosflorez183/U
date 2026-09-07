/*
 * ESP32: humedad capacitiva del suelo + sensor de lluvia + LCD I2C.
 *
 * Antes de cargar:
 * 1. Registra el dispositivo y genera una credencial desde Administración.
 * 2. Configura WIFI, API_URL, GROUP_ID, DEVICE_ID, API_KEY y SECRET_KEY.
 * 3. Calibra los cuatro valores *_RAW.
 * 4. Instala ArduinoJson y LiquidCrystal_I2C.
 */

#include <Arduino.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <LiquidCrystal_I2C.h>
#include <WiFi.h>
#include <Wire.h>
#include <time.h>

const char* WIFI_SSID = "CAMBIAR_SSID";
const char* WIFI_PASSWORD = "CAMBIAR_PASSWORD";
// Usa la IP LAN del computador/servidor; localhost apuntaría al propio ESP32.
const char* API_URL = "http://192.168.1.100:8000/api/v2/telemetry/samples";
const char* GROUP_ID = "grupo-01";
const char* DEVICE_ID = "esp32-grupo-01";
// Valores emitidos una sola vez por POST /api/v2/admin/credentials.
// No confirmes este archivo con credenciales reales en control de versiones.
const char* API_KEY = "CAMBIAR_API_KEY";
const char* SECRET_KEY = "CAMBIAR_SECRET_KEY";

constexpr uint8_t SOIL_ANALOG_PIN = 34;  // ADC1, compatible con WiFi.
constexpr uint8_t RAIN_ANALOG_PIN = 35;  // ADC1, compatible con WiFi.
constexpr uint8_t RAIN_DIGITAL_PIN = 27;
constexpr uint8_t I2C_SDA_PIN = 21;
constexpr uint8_t I2C_SCL_PIN = 22;
constexpr uint32_t SAMPLE_PERIOD_MS = 5000;

// Valores de demostración. Deben medirse con el montaje real.
constexpr int SOIL_DRY_RAW = 3200;
constexpr int SOIL_WET_RAW = 1300;
constexpr int RAIN_DRY_RAW = 4095;
constexpr int RAIN_WET_RAW = 1200;

LiquidCrystal_I2C lcd(0x27, 16, 2);
unsigned long lastSampleAt = 0;

float calibratedPercent(int raw, int dryRaw, int wetRaw) {
  if (dryRaw == wetRaw) return 0.0f;
  float percent = 100.0f * (dryRaw - raw) / (dryRaw - wetRaw);
  return constrain(percent, 0.0f, 100.0f);
}

String iso8601Now() {
  struct tm timeInfo;
  if (!getLocalTime(&timeInfo, 2000)) return "";
  char buffer[25];
  strftime(buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%SZ", &timeInfo);
  return String(buffer);
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

int postSample(
    int soilRaw,
    float soilPercent,
    int rainRaw,
    float rainPercent,
    bool rainDetected) {
  connectWiFi();
  if (WiFi.status() != WL_CONNECTED) return -1;

  String measuredAt = iso8601Now();
  if (measuredAt.isEmpty()) return -2;

  JsonDocument document;
  document["schema_version"] = "2.0";
  document["group_id"] = GROUP_ID;
  document["device_id"] = DEVICE_ID;
  document["measured_at"] = measuredAt;
  document["sampling_period_seconds"] = SAMPLE_PERIOD_MS / 1000;
  document["soil_moisture"]["raw_adc"] = soilRaw;
  document["soil_moisture"]["percent"] = round(soilPercent * 10.0f) / 10.0f;
  document["rain"]["raw_adc"] = rainRaw;
  document["rain"]["wetness_percent"] = round(rainPercent * 10.0f) / 10.0f;
  document["rain"]["detected"] = rainDetected;

  String body;
  serializeJson(document, body);
  HTTPClient http;
  http.setConnectTimeout(5000);
  http.setTimeout(5000);
  http.begin(API_URL);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", API_KEY);
  http.addHeader("X-Secret-Key", SECRET_KEY);
  int statusCode = http.POST(body);
  http.end();
  return statusCode;
}

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);
  pinMode(RAIN_DIGITAL_PIN, INPUT_PULLUP);
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  lcd.init();
  lcd.backlight();

  connectWiFi();
  // UTC; se necesita una hora válida para measured_at.
  configTime(0, 0, "pool.ntp.org", "time.google.com");
  lcd.clear();
  lcd.print("Sistema listo");
  delay(1000);
}

void loop() {
  if (millis() - lastSampleAt < SAMPLE_PERIOD_MS) return;
  lastSampleAt = millis();

  int soilRaw = analogRead(SOIL_ANALOG_PIN);
  int rainRaw = analogRead(RAIN_ANALOG_PIN);
  float soilPercent = calibratedPercent(soilRaw, SOIL_DRY_RAW, SOIL_WET_RAW);
  float rainPercent = calibratedPercent(rainRaw, RAIN_DRY_RAW, RAIN_WET_RAW);
  bool rainDetected = digitalRead(RAIN_DIGITAL_PIN) == LOW;

  int statusCode = postSample(
      soilRaw, soilPercent, rainRaw, rainPercent, rainDetected);

  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.printf("Suelo:%3.0f%%", soilPercent);
  lcd.setCursor(0, 1);
  lcd.printf("Lluv:%3.0f%% %d", rainPercent, statusCode);

  Serial.printf(
      "soil=%d/%.1f rain=%d/%.1f detected=%d http=%d\n",
      soilRaw, soilPercent, rainRaw, rainPercent, rainDetected, statusCode);
}
