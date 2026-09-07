# Construcción del dashboard Power BI

El parcial exige un `.pbix` conectado directamente a PostgreSQL. Power BI Desktop sólo está disponible en Windows; ejecuta estos pasos allí y guarda el resultado como `dashboard_agro_iot.pbix` en esta carpeta.

Para publicar PostgreSQL (con TimescaleDB opcional), FastAPI y Streamlit y conectar Power BI mediante TLS, sigue primero la [guía de alojamiento cloud y Power BI](../docs/ALOJAMIENTO_CLOUD_POWER_BI.md).

## Conexión

1. Levanta PostgreSQL y confirma el puerto publicado.
2. En Power BI Desktop: **Obtener datos → Base de datos PostgreSQL**.
3. Servidor local: `localhost:5432` —o el host/puerto desplegado—.
4. Base: `agro_iot`.
5. Elige **DirectQuery** si está disponible; Import con actualización sigue siendo conexión directa, pero confirma la interpretación con el docente.
6. Selecciona `vw_telemetry_wide` y `vw_powerbi_daily_summary`.
7. Usa un rol de sólo lectura en despliegue; no publiques credenciales dentro del repositorio.

## Cuatro indicadores mínimos

Usa las medidas de `MEDIDAS_DAX.md`:

1. Total de muestras.
2. Humedad promedio del suelo.
3. Humedad promedio del sensor de lluvia.
4. Detecciones de lluvia.

Puede añadirse alertas de calidad como quinto KPI.

## Seis gráficos mínimos

1. Línea: `measured_at` vs `soil_moisture_percent`.
2. Línea: `measured_at` vs `rain_wetness_percent`.
3. Columnas: cantidad de muestras por `soil_status`.
4. Dispersión: suelo vs lluvia, color por `device_id`.
5. Dona: `rain_detected` sí/no.
6. Columnas temporales: muestras y alertas por `day` desde la vista diaria.

## Filtros/segmentadores

Incluye al menos:

- Rango de `measured_at` o `day`.
- `device_id`.
- Recomendado adicional: `group_id`.

## Diseño

Paleta sugerida: verde `#2E7D32`, azul lluvia `#1976D2`, fondo `#F5F7F5`, advertencia `#F9A825`. Primera fila de KPIs, segunda de tendencias, tercera de distribución/calidad. Añade título, fecha de actualización y unidades.

## Validación final

- Cambia un filtro y comprueba que KPIs y seis gráficos respondan.
- Inserta una muestra nueva y actualiza/DirectQuery para comprobar conexión real.
- Verifica que el origen sea PostgreSQL, no CSV/Excel.
- Guarda y vuelve a abrir el `.pbix` antes de entregar.
