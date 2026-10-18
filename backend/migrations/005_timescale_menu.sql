-- 005: TimescaleDB para el Taller 1 Corte 2 + vistas de analítica del menú.
-- La hypertable de lecturas es sensor_measurements (una fila por magnitud leída).
-- Con el DHT22 cada 20 s se insertan 2 filas (temperatura y humedad):
--   6/min, 360/h, 8.640/día por dispositivo -> chunk_time_interval = 1 día.
-- telemetry_samples se conserva como tabla estándar porque otras tablas la
-- referencian con FOREIGN KEY (Timescale no permite claves hacia una hypertable).
-- Nota: sin BEGIN/COMMIT a propósito; set_chunk_time_interval no requiere
-- transacción y así el archivo puede correrse en la nube (Neon) o en Docker.

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Frecuencia del taller: una lectura cada 20 segundos.
DO $$
DECLARE
    constraint_name TEXT;
BEGIN
    SELECT conname INTO constraint_name
    FROM pg_constraint
    WHERE conrelid = 'telemetry_samples'::regclass
      AND contype = 'c'
      AND pg_get_constraintdef(oid) LIKE '%sampling_period_seconds%';
    IF constraint_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE telemetry_samples DROP CONSTRAINT %I', constraint_name);
    END IF;
END
$$;

ALTER TABLE telemetry_samples
    ADD CONSTRAINT telemetry_samples_sampling_period_seconds_check
    CHECK (sampling_period_seconds IN (5, 10, 20, 25, 30));

-- Mediciones por sensor como hypertable con un chunk por día.
-- En BD nuevas (Neon u otro PostgreSQL con TimescaleDB) la extension recien se
-- crea aqui, por eso se crea la hypertable en esta migracion; en Docker ya
-- existe y es un no-op.
SELECT create_hypertable(
    'sensor_measurements',
    by_range('measured_at', INTERVAL '1 day'),
    if_not_exists => TRUE,
    migrate_data => FALSE
);

SELECT set_chunk_time_interval('sensor_measurements', INTERVAL '1 day');

-- Estadísticos por hora (Exploración y menú opción 2/4).
CREATE OR REPLACE VIEW vw_hourly_stats AS
SELECT
    date_trunc('hour', measured_at) AS hour,
    group_id,
    device_id,
    COUNT(*) AS sample_count,
    AVG(temperature_celsius) AS avg_temperature_celsius,
    MIN(temperature_celsius) AS min_temperature_celsius,
    MAX(temperature_celsius) AS max_temperature_celsius,
    STDDEV_POP(temperature_celsius) AS stddev_temperature_celsius,
    AVG(humidity_percent) AS avg_humidity_percent,
    MIN(humidity_percent) AS min_humidity_percent,
    MAX(humidity_percent) AS max_humidity_percent,
    STDDEV_POP(humidity_percent) AS stddev_humidity_percent
FROM vw_telemetry_wide
GROUP BY 1, 2, 3;

-- Estadísticos por día (menú opción 3/4 y dashboard KNIME).
CREATE OR REPLACE VIEW vw_daily_stats AS
SELECT
    date_trunc('day', measured_at) AS day,
    group_id,
    device_id,
    COUNT(*) AS sample_count,
    AVG(temperature_celsius) AS avg_temperature_celsius,
    MIN(temperature_celsius) AS min_temperature_celsius,
    MAX(temperature_celsius) AS max_temperature_celsius,
    STDDEV_POP(temperature_celsius) AS stddev_temperature_celsius,
    AVG(humidity_percent) AS avg_humidity_percent,
    MIN(humidity_percent) AS min_humidity_percent,
    MAX(humidity_percent) AS max_humidity_percent,
    STDDEV_POP(humidity_percent) AS stddev_humidity_percent
FROM vw_telemetry_wide
GROUP BY 1, 2, 3;

-- Última lectura por dispositivo (menú opción 1, tiempo real).
CREATE OR REPLACE VIEW vw_menu_realtime AS
SELECT DISTINCT ON (device_id)
    group_id,
    device_id,
    measured_at,
    temperature_celsius,
    humidity_percent,
    temp_status,
    humidity_status
FROM vw_telemetry_wide
ORDER BY device_id, measured_at DESC;

-- Estado de conexión de cada dispositivo (menú opción 7).
CREATE OR REPLACE VIEW vw_device_status AS
SELECT
    device.external_id AS device_id,
    grp.code AS group_id,
    device.name AS device_name,
    device.last_seen_at,
    (
        device.last_seen_at IS NOT NULL
        AND device.last_seen_at >= now() - INTERVAL '60 seconds'
    ) AS online
FROM devices device
JOIN iot_groups grp ON grp.id = device.group_id
WHERE device.active;

-- Alertas ambientales: estados fuera de confort o con marcas de calidad.
CREATE OR REPLACE VIEW vw_alerts AS
SELECT
    sample.id AS sample_id,
    sample.group_id,
    sample.device_id,
    sample.measured_at,
    sample.temperature_celsius,
    sample.humidity_percent,
    sample.temp_status,
    sample.humidity_status,
    (sample.temperature_celsius < 18 OR sample.temperature_celsius > 28) AS temperature_alert,
    (sample.humidity_percent < 30 OR sample.humidity_percent >= 70) AS humidity_alert,
    cardinality(sample.quality_flags) > 0 AS quality_alert
FROM vw_telemetry_wide sample
WHERE sample.temp_status <> 'COMFORT'
   OR sample.humidity_status <> 'COMFORT'
   OR cardinality(sample.quality_flags) > 0;

-- Atípicos: más de 2 desviaciones estándar del promedio del día (menú opción 5).
CREATE OR REPLACE VIEW vw_outliers AS
WITH daily AS (
    SELECT
        wide.device_id,
        date_trunc('day', wide.measured_at) AS day,
        AVG(wide.temperature_celsius) AS avg_temperature_celsius,
        STDDEV_POP(wide.temperature_celsius) AS stddev_temperature_celsius,
        AVG(wide.humidity_percent) AS avg_humidity_percent,
        STDDEV_POP(wide.humidity_percent) AS stddev_humidity_percent
    FROM vw_telemetry_wide wide
    GROUP BY 1, 2
)
SELECT
    wide.id AS sample_id,
    wide.group_id,
    wide.device_id,
    wide.measured_at,
    wide.temperature_celsius,
    wide.humidity_percent,
    daily.avg_temperature_celsius,
    daily.stddev_temperature_celsius,
    daily.avg_humidity_percent,
    daily.stddev_humidity_percent
FROM vw_telemetry_wide wide
JOIN daily
  ON daily.device_id = wide.device_id
 AND daily.day = date_trunc('day', wide.measured_at)
WHERE (daily.stddev_temperature_celsius > 0
       AND abs(wide.temperature_celsius - daily.avg_temperature_celsius)
           > 2 * daily.stddev_temperature_celsius)
   OR (daily.stddev_humidity_percent > 0
       AND abs(wide.humidity_percent - daily.avg_humidity_percent)
           > 2 * daily.stddev_humidity_percent);

INSERT INTO schema_migrations(version) VALUES ('005_timescale_menu')
ON CONFLICT (version) DO NOTHING;
