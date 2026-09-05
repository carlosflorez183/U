# Medidas DAX sugeridas

Ajusta el nombre de tabla si Power BI lo importa con otro alias.

```DAX
Total Muestras =
COUNTROWS(vw_telemetry_wide)

Humedad Suelo Promedio =
AVERAGE(vw_telemetry_wide[soil_moisture_percent])

Humedad Lluvia Promedio =
AVERAGE(vw_telemetry_wide[rain_wetness_percent])

Detecciones de Lluvia =
CALCULATE(
    COUNTROWS(vw_telemetry_wide),
    vw_telemetry_wide[rain_detected] = TRUE()
)

Última Medición =
MAX(vw_telemetry_wide[measured_at])
```

Formatea porcentajes con uno o dos decimales y `Última Medición` como fecha/hora.
