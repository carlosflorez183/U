# Medidas DAX sugeridas

Ajusta el nombre de tabla si Power BI lo importa con otro alias.

```DAX
Total Muestras =
COUNTROWS(vw_telemetry_wide)

Temperatura Promedio =
AVERAGE(vw_telemetry_wide[temperature_celsius])

Humedad Promedio =
AVERAGE(vw_telemetry_wide[humidity_percent])

Muestras Humedas (>=70%) =
CALCULATE(
    COUNTROWS(vw_telemetry_wide),
    vw_telemetry_wide[humidity_percent] >= 70
)

Última Medición =
MAX(vw_telemetry_wide[measured_at])
```

Formatea porcentajes con uno o dos decimales y `Última Medición` como fecha/hora.
