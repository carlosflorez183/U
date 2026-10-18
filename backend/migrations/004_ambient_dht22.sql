\set ON_ERROR_STOP on

BEGIN;

-- 004: migrar de suelo/lluvia (ADC) a ambiental DHT22 (temperatura/humedad).
-- Idempotente: puede correrse varias veces y en BD frescas o existentes.

INSERT INTO sensor_types(code, name, unit, value_kind, min_value, max_value) VALUES
    ('temperature', 'Temperatura del aire DHT22', 'celsius', 'numeric', -40, 80),
    ('humidity', 'Humedad relativa del aire DHT22', 'percent', 'numeric', 0, 100)
ON CONFLICT (code) DO UPDATE SET
    name = EXCLUDED.name,
    unit = EXCLUDED.unit,
    value_kind = EXCLUDED.value_kind,
    min_value = EXCLUDED.min_value,
    max_value = EXCLUDED.max_value;

-- Vistas dependen de columnas de estado: dropear para poder alterar la tabla.
DROP VIEW IF EXISTS vw_outliers;
DROP VIEW IF EXISTS vw_alerts;
DROP VIEW IF EXISTS vw_menu_realtime;
DROP VIEW IF EXISTS vw_daily_stats;
DROP VIEW IF EXISTS vw_hourly_stats;
DROP VIEW IF EXISTS vw_powerbi_daily_summary;
DROP VIEW IF EXISTS vw_telemetry_wide;

-- Nuevas columnas de estado ambiental.
ALTER TABLE telemetry_samples
    ADD COLUMN IF NOT EXISTS temp_status VARCHAR(16),
    ADD COLUMN IF NOT EXISTS humidity_status VARCHAR(16);

-- Backfill desde esquema antiguo si existe.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='telemetry_samples' AND column_name='soil_status') THEN
        EXECUTE $q$
            UPDATE telemetry_samples
            SET humidity_status = COALESCE(humidity_status,
                CASE soil_status WHEN 'DRY' THEN 'DRY' WHEN 'WET' THEN 'HUMID' ELSE 'COMFORT' END),
                temp_status = COALESCE(temp_status, 'COMFORT')
            WHERE temp_status IS NULL OR humidity_status IS NULL
        $q$;
    ELSE
        EXECUTE $q$
            UPDATE telemetry_samples
            SET temp_status = COALESCE(temp_status, 'COMFORT'),
                humidity_status = COALESCE(humidity_status, 'COMFORT')
            WHERE temp_status IS NULL OR humidity_status IS NULL
        $q$;
    END IF;
END
$$;

-- Hacer NOT NULL tras backfill (solo si no hay nulos).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM telemetry_samples WHERE temp_status IS NULL) THEN
        BEGIN
            ALTER TABLE telemetry_samples ALTER COLUMN temp_status SET NOT NULL;
        EXCEPTION WHEN others THEN NULL;
        END;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM telemetry_samples WHERE humidity_status IS NULL) THEN
        BEGIN
            ALTER TABLE telemetry_samples ALTER COLUMN humidity_status SET NOT NULL;
        EXCEPTION WHEN others THEN NULL;
        END;
    END IF;
END
$$;

-- Checks de estado ambiental (nombres fijos, IF NOT EXISTS vía pg_constraint).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='telemetry_samples_temp_status_check') THEN
        ALTER TABLE telemetry_samples
            ADD CONSTRAINT telemetry_samples_temp_status_check
            CHECK (temp_status IN ('COLD','COMFORT','HOT'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='telemetry_samples_humidity_status_check') THEN
        ALTER TABLE telemetry_samples
            ADD CONSTRAINT telemetry_samples_humidity_status_check
            CHECK (humidity_status IN ('DRY','COMFORT','HUMID'));
    END IF;
END
$$;

-- Eliminar columnas antiguas suelo/lluvia (si existen).
ALTER TABLE telemetry_samples DROP COLUMN IF EXISTS soil_status;
ALTER TABLE telemetry_samples DROP COLUMN IF EXISTS rain_status;

-- sensor_measurements: DHT22 no tiene ADC -> raw_adc nullable, numeric_value -50..100.
ALTER TABLE sensor_measurements ALTER COLUMN raw_adc DROP NOT NULL;

DO $$
DECLARE r RECORD;
BEGIN
    FOR r IN SELECT conname FROM pg_constraint
             WHERE conrelid='sensor_measurements'::regclass AND contype='c' LOOP
        IF r.conname LIKE '%raw_adc%' OR r.conname LIKE '%numeric_value%' THEN
            EXECUTE format('ALTER TABLE sensor_measurements DROP CONSTRAINT IF EXISTS %I', r.conname);
        END IF;
    END LOOP;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='sensor_measurements_raw_adc_range') THEN
        ALTER TABLE sensor_measurements
            ADD CONSTRAINT sensor_measurements_raw_adc_range
            CHECK (raw_adc IS NULL OR (raw_adc BETWEEN 0 AND 4095));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='sensor_measurements_numeric_range') THEN
        ALTER TABLE sensor_measurements
            ADD CONSTRAINT sensor_measurements_numeric_range
            CHECK (numeric_value BETWEEN -50 AND 100);
    END IF;
END
$$;

-- Vista ancha ambiental + alias de compatibilidad suelo/lluvia.
CREATE OR REPLACE VIEW vw_telemetry_wide AS
SELECT
    sample.id,
    grp.code AS group_id,
    dev.external_id AS device_id,
    sample.sequence,
    sample.schema_version,
    sample.measured_at,
    sample.received_at,
    sample.sampling_period_seconds,
    temp.numeric_value AS temperature_celsius,
    hum.numeric_value AS humidity_percent,
    sample.temp_status,
    sample.humidity_status,
    -- Compat: dashboards antiguos siguen leyendo estas columnas.
    hum.numeric_value AS soil_moisture_percent,
    0 AS soil_raw_adc,
    sample.humidity_status AS soil_status,
    hum.numeric_value AS rain_wetness_percent,
    0 AS rain_raw_adc,
    (hum.numeric_value >= 70.0) AS rain_detected,
    CASE WHEN hum.numeric_value >= 70.0 THEN 'RAIN_DETECTED' ELSE 'NO_RAIN' END AS rain_status,
    ARRAY(
        SELECT flag.flag_code
        FROM sample_quality_flags flag
        WHERE flag.sample_id = sample.id
        ORDER BY flag.flag_code
    ) AS quality_flags,
    COALESCE(sample.device_alias_at_ingest, dev.name) AS device_alias,
    sample.credential_alias_at_ingest AS inserted_by_alias,
    sample.ingest_credential_id,
    sample.payload_sha256
FROM telemetry_samples sample
JOIN devices dev ON dev.id = sample.device_id
JOIN iot_groups grp ON grp.id = dev.group_id
LEFT JOIN LATERAL (
    SELECT measurement.numeric_value
    FROM sensor_measurements measurement
    JOIN sensors sensor ON sensor.id = measurement.sensor_id
    JOIN sensor_types sensor_type ON sensor_type.id = sensor.sensor_type_id
    WHERE measurement.sample_id = sample.id
      AND sensor_type.code IN ('temperature','soil_moisture')
    ORDER BY measurement.measured_at DESC
    LIMIT 1
) temp ON TRUE
LEFT JOIN LATERAL (
    SELECT measurement.numeric_value
    FROM sensor_measurements measurement
    JOIN sensors sensor ON sensor.id = measurement.sensor_id
    JOIN sensor_types sensor_type ON sensor_type.id = sensor.sensor_type_id
    WHERE measurement.sample_id = sample.id
      AND sensor_type.code IN ('humidity','rain_wetness')
    ORDER BY measurement.measured_at DESC
    LIMIT 1
) hum ON TRUE;

CREATE OR REPLACE VIEW vw_powerbi_daily_summary AS
SELECT
    date_trunc('day', measured_at, 'UTC') AS day,
    group_id,
    device_id,
    COUNT(*) AS sample_count,
    AVG(temperature_celsius) AS avg_temperature_celsius,
    MIN(temperature_celsius) AS min_temperature_celsius,
    MAX(temperature_celsius) AS max_temperature_celsius,
    AVG(humidity_percent) AS avg_humidity_percent,
    MIN(humidity_percent) AS min_humidity_percent,
    MAX(humidity_percent) AS max_humidity_percent,
    -- Compat con paneles antiguos.
    AVG(humidity_percent) AS avg_soil_moisture_percent,
    MIN(humidity_percent) AS min_soil_moisture_percent,
    MAX(humidity_percent) AS max_soil_moisture_percent,
    AVG(humidity_percent) AS avg_rain_wetness_percent,
    COUNT(*) FILTER (WHERE humidity_percent >= 70.0) AS rain_detection_count,
    COUNT(*) FILTER (WHERE cardinality(quality_flags) > 0) AS quality_alert_count
FROM vw_telemetry_wide
GROUP BY day, group_id, device_id;

INSERT INTO schema_migrations(version) VALUES ('004_ambient_dht22')
ON CONFLICT (version) DO NOTHING;

COMMIT;
