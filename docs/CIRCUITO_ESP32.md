# Circuito ESP32: lluvia y humedad del suelo

## Componentes

- ESP32 DevKit.
- Sensor capacitivo de humedad del suelo con salida analógica.
- Módulo detector de lluvia con salida analógica y digital.
- LCD I2C 16x2, normalmente en dirección `0x27`.
- Protoboard, alimentación estable y cable UTP según el documento del parcial.

## Cableado de referencia

| Componente | Señal | ESP32 |
|---|---|---|
| Humedad de suelo | AO | GPIO 34 (ADC1) |
| Humedad de suelo | VCC | Según especificación del módulo; preferir 3.3 V |
| Humedad de suelo | GND | GND común |
| Sensor de lluvia | AO | GPIO 35 (ADC1) |
| Sensor de lluvia | DO | GPIO 27 |
| Sensor de lluvia | VCC | Según especificación del módulo; preferir 3.3 V |
| Sensor de lluvia | GND | GND común |
| LCD I2C | SDA | GPIO 21 |
| LCD I2C | SCL | GPIO 22 |
| LCD I2C | GND | GND común |

> Los GPIO 34 y 35 son entradas y pertenecen a ADC1. Se usan porque ADC2 presenta conflictos cuando el WiFi del ESP32 está activo.

## Precaución de voltaje

Los GPIO del ESP32 no toleran 5 V. Verifica con multímetro que AO, DO, SDA y SCL no superen 3.3 V. Algunos LCD I2C alimentados a 5 V necesitan conversión de nivel lógico o modificación de pull-ups.

## Calibración del sensor capacitivo

1. Registra varias lecturas con el sensor al aire o en suelo completamente seco: `SOIL_DRY_RAW`.
2. Registra varias lecturas en suelo saturado o según el procedimiento del fabricante: `SOIL_WET_RAW`.
3. Usa el promedio, no una lectura individual.
4. Repite para cada tipo de suelo y documenta temperatura, recipiente y profundidad.
5. Modifica las constantes del firmware.

La conversión inicial es lineal y limitada a 0–100 %:

```text
porcentaje = 100 × (raw_seco - raw_actual) / (raw_seco - raw_humedo)
```

Este porcentaje representa una escala calibrada del sensor, no necesariamente contenido volumétrico de agua sin una calibración agronómica adicional.

## Calibración de lluvia

Registra `RAIN_DRY_RAW` con la placa limpia y seca, y `RAIN_WET_RAW` con una película de agua reproducible. El porcentaje representa superficie/humedad detectada, no precipitación en milímetros.

La salida digital depende del potenciómetro del comparador del módulo. Ajusta el umbral y comprueba que sea coherente con `wetness_percent`; la API marca discrepancias con `RAIN_DETECTION_MISMATCH`.

## Frecuencia

El firmware usa 5 segundos, permitido por el DOCX. Para 10 segundos cambia `SAMPLE_PERIOD_MS` a `10000`; la API solo acepta 5 o 10.
