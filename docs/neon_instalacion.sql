-- =====================================================================
-- Instalacion completa en Neon (PostgreSQL + TimescaleDB) para el taller.
-- Pasos: 1) abrir el SQL Editor de Neon; 2) pegar TODO este archivo;
--        3) ejecutar una sola vez; 4) verificar con las consultas del
--        final. Generado desde backend/migrations/001..005 con
--        scripts/generar_instalacion_neon.py (sin metacomandos de psql).
-- =====================================================================

-- ===== 001_initial.sql =====
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_available_extensions
        WHERE name = 'timescaledb'
    ) THEN
        EXECUTE 'CREATE EXTENSION IF NOT EXISTS timescaledb';
    ELSE
        RAISE NOTICE 'TimescaleDB no está disponible; se usará PostgreSQL estándar.';
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(32) PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS iot_groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS devices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id UUID NOT NULL REFERENCES iot_groups(id) ON DELETE RESTRICT,
    external_id VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(120) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS devices_group_idx ON devices(group_id);

CREATE TABLE IF NOT EXISTS sensor_types (
    id SMALLSERIAL PRIMARY KEY,
    code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(120) NOT NULL,
    unit VARCHAR(24),
    value_kind VARCHAR(16) NOT NULL CHECK (value_kind IN ('numeric', 'boolean')),
    min_value DOUBLE PRECISION,
    max_value DOUBLE PRECISION,
    CHECK (min_value IS NULL OR max_value IS NULL OR min_value <= max_value)
);

CREATE TABLE IF NOT EXISTS sensors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    sensor_type_id SMALLINT NOT NULL REFERENCES sensor_types(id) ON DELETE RESTRICT,
    external_id VARCHAR(64) NOT NULL,
    pin VARCHAR(24),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    installed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(device_id, external_id)
);
CREATE INDEX IF NOT EXISTS sensors_device_idx ON sensors(device_id);
CREATE INDEX IF NOT EXISTS sensors_type_idx ON sensors(sensor_type_id);

CREATE TABLE IF NOT EXISTS calibrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sensor_id UUID NOT NULL REFERENCES sensors(id) ON DELETE CASCADE,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    valid_from TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_to TIMESTAMPTZ,
    raw_dry INTEGER CHECK (raw_dry BETWEEN 0 AND 4095),
    raw_wet INTEGER CHECK (raw_wet BETWEEN 0 AND 4095),
    formula TEXT NOT NULL DEFAULT 'percentage_reported_by_device',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(sensor_id, version),
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE TABLE IF NOT EXISTS telemetry_samples (
    id UUID PRIMARY KEY,
    device_id UUID NOT NULL REFERENCES devices(id) ON DELETE RESTRICT,
    sequence BIGINT NOT NULL CHECK (sequence >= 0),
    schema_version VARCHAR(12) NOT NULL CHECK (schema_version = '2.0'),
    measured_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sampling_period_seconds SMALLINT NOT NULL CHECK (sampling_period_seconds IN (5, 10)),
    soil_status VARCHAR(16) NOT NULL CHECK (soil_status IN ('DRY', 'OPTIMAL', 'WET')),
    rain_status VARCHAR(24) NOT NULL CHECK (rain_status IN ('RAIN_DETECTED', 'NO_RAIN')),
    UNIQUE(device_id, sequence)
);
CREATE INDEX IF NOT EXISTS telemetry_samples_measured_idx ON telemetry_samples(measured_at DESC);
CREATE INDEX IF NOT EXISTS telemetry_samples_device_time_idx ON telemetry_samples(device_id, measured_at DESC);

CREATE TABLE IF NOT EXISTS sensor_measurements (
    sample_id UUID NOT NULL REFERENCES telemetry_samples(id) ON DELETE CASCADE,
    sensor_id UUID NOT NULL REFERENCES sensors(id) ON DELETE RESTRICT,
    calibration_id UUID REFERENCES calibrations(id) ON DELETE SET NULL,
    measured_at TIMESTAMPTZ NOT NULL,
    raw_adc SMALLINT NOT NULL CHECK (raw_adc BETWEEN 0 AND 4095),
    numeric_value DOUBLE PRECISION NOT NULL CHECK (numeric_value BETWEEN 0 AND 100),
    boolean_value BOOLEAN,
    PRIMARY KEY(sample_id, sensor_id, measured_at)
);
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_extension
        WHERE extname = 'timescaledb'
    ) THEN
        EXECUTE $hypertable$
            SELECT create_hypertable(
                'sensor_measurements',
                by_range('measured_at', INTERVAL '7 days'),
                if_not_exists => TRUE,
                migrate_data => TRUE
            )
        $hypertable$;
    ELSE
        RAISE NOTICE 'sensor_measurements permanecerá como tabla PostgreSQL estándar.';
    END IF;
END
$$;
CREATE INDEX IF NOT EXISTS sensor_measurements_sensor_time_idx
    ON sensor_measurements(sensor_id, measured_at DESC);
CREATE INDEX IF NOT EXISTS sensor_measurements_sample_idx
    ON sensor_measurements(sample_id, measured_at DESC);

CREATE TABLE IF NOT EXISTS quality_flag_types (
    code VARCHAR(48) PRIMARY KEY,
    description VARCHAR(240) NOT NULL,
    severity VARCHAR(12) NOT NULL CHECK (severity IN ('INFO', 'WARNING', 'CRITICAL'))
);

CREATE TABLE IF NOT EXISTS sample_quality_flags (
    sample_id UUID NOT NULL REFERENCES telemetry_samples(id) ON DELETE CASCADE,
    flag_code VARCHAR(48) NOT NULL REFERENCES quality_flag_types(code) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(sample_id, flag_code)
);
CREATE INDEX IF NOT EXISTS sample_quality_flags_code_idx ON sample_quality_flags(flag_code);

CREATE TABLE IF NOT EXISTS legacy_records (
    id UUID PRIMARY KEY,
    data JSONB NOT NULL CHECK (jsonb_typeof(data) = 'object'),
    source VARCHAR(120),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS legacy_records_created_idx ON legacy_records(created_at DESC);

INSERT INTO sensor_types(code, name, unit, value_kind, min_value, max_value) VALUES
    ('soil_moisture', 'Humedad capacitiva del suelo', 'percent', 'numeric', 0, 100),
    ('rain_wetness', 'Humedad superficial del sensor de lluvia', 'percent', 'numeric', 0, 100)
ON CONFLICT (code) DO UPDATE SET
    name = EXCLUDED.name,
    unit = EXCLUDED.unit,
    value_kind = EXCLUDED.value_kind,
    min_value = EXCLUDED.min_value,
    max_value = EXCLUDED.max_value;

INSERT INTO quality_flag_types(code, description, severity) VALUES
    ('SOIL_ADC_RAIL', 'ADC del sensor de suelo en un extremo eléctrico', 'WARNING'),
    ('RAIN_ADC_RAIL', 'ADC del sensor de lluvia en un extremo eléctrico', 'WARNING'),
    ('TIMESTAMP_FUTURE', 'La marca de tiempo está adelantada respecto al servidor', 'WARNING'),
    ('STALE_SAMPLE', 'La muestra tiene más de un día de antigüedad', 'WARNING'),
    ('RAIN_DETECTION_MISMATCH', 'La señal digital no coincide con el porcentaje de lluvia', 'WARNING')
ON CONFLICT (code) DO UPDATE SET
    description = EXCLUDED.description,
    severity = EXCLUDED.severity;

DROP VIEW IF EXISTS vw_telemetry_wide CASCADE;
CREATE VIEW vw_telemetry_wide AS
SELECT
    sample.id,
    grp.code AS group_id,
    dev.external_id AS device_id,
    sample.sequence,
    sample.schema_version,
    sample.measured_at,
    sample.received_at,
    sample.sampling_period_seconds,
    soil.raw_adc AS soil_raw_adc,
    soil.numeric_value AS soil_moisture_percent,
    sample.soil_status,
    rain.raw_adc AS rain_raw_adc,
    rain.numeric_value AS rain_wetness_percent,
    COALESCE(rain.boolean_value, FALSE) AS rain_detected,
    sample.rain_status,
    ARRAY(
        SELECT flag.flag_code
        FROM sample_quality_flags flag
        WHERE flag.sample_id = sample.id
        ORDER BY flag.flag_code
    ) AS quality_flags
FROM telemetry_samples sample
JOIN devices dev ON dev.id = sample.device_id
JOIN iot_groups grp ON grp.id = dev.group_id
LEFT JOIN LATERAL (
    SELECT measurement.raw_adc, measurement.numeric_value
    FROM sensor_measurements measurement
    JOIN sensors sensor ON sensor.id = measurement.sensor_id
    JOIN sensor_types sensor_type ON sensor_type.id = sensor.sensor_type_id
    WHERE measurement.sample_id = sample.id
      AND sensor_type.code = 'soil_moisture'
    ORDER BY measurement.measured_at DESC
    LIMIT 1
) soil ON TRUE
LEFT JOIN LATERAL (
    SELECT measurement.raw_adc, measurement.numeric_value, measurement.boolean_value
    FROM sensor_measurements measurement
    JOIN sensors sensor ON sensor.id = measurement.sensor_id
    JOIN sensor_types sensor_type ON sensor_type.id = sensor.sensor_type_id
    WHERE measurement.sample_id = sample.id
      AND sensor_type.code = 'rain_wetness'
    ORDER BY measurement.measured_at DESC
    LIMIT 1
) rain ON TRUE;

DROP VIEW IF EXISTS vw_powerbi_daily_summary CASCADE;
CREATE VIEW vw_powerbi_daily_summary AS
SELECT
    date_trunc('day', measured_at, 'UTC') AS day,
    group_id,
    device_id,
    COUNT(*) AS sample_count,
    AVG(soil_moisture_percent) AS avg_soil_moisture_percent,
    MIN(soil_moisture_percent) AS min_soil_moisture_percent,
    MAX(soil_moisture_percent) AS max_soil_moisture_percent,
    AVG(rain_wetness_percent) AS avg_rain_wetness_percent,
    COUNT(*) FILTER (WHERE rain_detected) AS rain_detection_count,
    COUNT(*) FILTER (WHERE cardinality(quality_flags) > 0) AS quality_alert_count
FROM vw_telemetry_wide
GROUP BY day, group_id, device_id;

INSERT INTO schema_migrations(version) VALUES ('001_initial')
ON CONFLICT (version) DO NOTHING;

-- ===== 002_device_credentials.sql =====
BEGIN;

CREATE TABLE IF NOT EXISTS device_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    alias VARCHAR(120) NOT NULL CHECK (length(btrim(alias)) > 0),
    api_key_digest CHAR(64) NOT NULL UNIQUE,
    api_key_prefix VARCHAR(20) NOT NULL,
    secret_salt BYTEA NOT NULL,
    secret_hash BYTEA NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    CHECK ((active AND revoked_at IS NULL) OR (NOT active))
);
CREATE INDEX IF NOT EXISTS device_credentials_device_idx
    ON device_credentials(device_id, active);

ALTER TABLE telemetry_samples
    ADD COLUMN IF NOT EXISTS ingest_credential_id UUID,
    ADD COLUMN IF NOT EXISTS device_alias_at_ingest VARCHAR(120),
    ADD COLUMN IF NOT EXISTS credential_alias_at_ingest VARCHAR(120),
    ADD COLUMN IF NOT EXISTS payload_sha256 CHAR(64);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'telemetry_samples_ingest_credential_fk'
    ) THEN
        ALTER TABLE telemetry_samples
            ADD CONSTRAINT telemetry_samples_ingest_credential_fk
            FOREIGN KEY (ingest_credential_id)
            REFERENCES device_credentials(id)
            ON DELETE SET NULL;
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS telemetry_samples_credential_idx
    ON telemetry_samples(ingest_credential_id, measured_at DESC);

UPDATE telemetry_samples sample
SET device_alias_at_ingest = device.name
FROM devices device
WHERE sample.device_id = device.id
  AND sample.device_alias_at_ingest IS NULL;

-- Solo aplica la vista suelo/lluvia si el esquema aún no migró a DHT22 (004).
-- En re-ejecuciones con temp_status existente, 004 ya dejó la vista ambiental.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='telemetry_samples' AND column_name='soil_status') THEN
        EXECUTE $view$
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
            soil.raw_adc AS soil_raw_adc,
            soil.numeric_value AS soil_moisture_percent,
            sample.soil_status,
            rain.raw_adc AS rain_raw_adc,
            rain.numeric_value AS rain_wetness_percent,
            COALESCE(rain.boolean_value, FALSE) AS rain_detected,
            sample.rain_status,
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
            SELECT measurement.raw_adc, measurement.numeric_value
            FROM sensor_measurements measurement
            JOIN sensors sensor ON sensor.id = measurement.sensor_id
            JOIN sensor_types sensor_type ON sensor_type.id = sensor.sensor_type_id
            WHERE measurement.sample_id = sample.id
              AND sensor_type.code = 'soil_moisture'
            ORDER BY measurement.measured_at DESC
            LIMIT 1
        ) soil ON TRUE
        LEFT JOIN LATERAL (
            SELECT measurement.raw_adc, measurement.numeric_value, measurement.boolean_value
            FROM sensor_measurements measurement
            JOIN sensors sensor ON sensor.id = measurement.sensor_id
            JOIN sensor_types sensor_type ON sensor_type.id = sensor.sensor_type_id
            WHERE measurement.sample_id = sample.id
              AND sensor_type.code = 'rain_wetness'
            ORDER BY measurement.measured_at DESC
            LIMIT 1
        ) rain ON TRUE
        $view$;
    ELSE
        RAISE NOTICE 'vw_telemetry_wide ya es ambiental (004); se omite vista 002.';
    END IF;
END
$$;

INSERT INTO schema_migrations(version) VALUES ('002_device_credentials')
ON CONFLICT (version) DO NOTHING;

COMMIT;

-- ===== 003_postgresql_portability.sql =====
BEGIN;

-- Solo aplica el resumen suelo/lluvia si aún no migró a DHT22 (004).
DO $$
BEGIN
    IF to_regclass('public.vw_telemetry_wide') IS NULL
       OR NOT EXISTS (SELECT 1 FROM information_schema.columns
                      WHERE table_name='vw_telemetry_wide'
                        AND column_name='temperature_celsius') THEN
        EXECUTE $view$
        CREATE OR REPLACE VIEW vw_powerbi_daily_summary AS
        SELECT
            date_trunc('day', measured_at, 'UTC') AS day,
            group_id,
            device_id,
            COUNT(*) AS sample_count,
            AVG(soil_moisture_percent) AS avg_soil_moisture_percent,
            MIN(soil_moisture_percent) AS min_soil_moisture_percent,
            MAX(soil_moisture_percent) AS max_soil_moisture_percent,
            AVG(rain_wetness_percent) AS avg_rain_wetness_percent,
            COUNT(*) FILTER (WHERE rain_detected) AS rain_detection_count,
            COUNT(*) FILTER (WHERE cardinality(quality_flags) > 0) AS quality_alert_count
        FROM vw_telemetry_wide
        GROUP BY day, group_id, device_id
        $view$;
    ELSE
        RAISE NOTICE 'vw_powerbi_daily_summary ya es ambiental (004); se omite vista 003.';
    END IF;
END
$$;

INSERT INTO schema_migrations(version) VALUES ('003_postgresql_portability')
ON CONFLICT (version) DO NOTHING;

COMMIT;

-- ===== 004_ambient_dht22.sql =====
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

-- ===== 005_timescale_menu.sql =====
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
