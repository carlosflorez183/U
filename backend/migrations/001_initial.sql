\set ON_ERROR_STOP on

CREATE EXTENSION IF NOT EXISTS timescaledb;

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
SELECT create_hypertable(
    'sensor_measurements',
    by_range('measured_at', INTERVAL '7 days'),
    if_not_exists => TRUE,
    migrate_data => TRUE
);
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

SELECT CASE
    WHEN to_regclass('public.vw_telemetry_wide') IS NULL THEN 'true'
    ELSE 'false'
END AS create_vw_telemetry_wide \gset
\if :create_vw_telemetry_wide
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
\endif

SELECT CASE
    WHEN to_regclass('public.vw_powerbi_daily_summary') IS NULL THEN 'true'
    ELSE 'false'
END AS create_vw_powerbi_daily_summary \gset
\if :create_vw_powerbi_daily_summary
CREATE VIEW vw_powerbi_daily_summary AS
SELECT
    time_bucket(INTERVAL '1 day', measured_at) AS day,
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
\endif

INSERT INTO schema_migrations(version) VALUES ('001_initial')
ON CONFLICT (version) DO NOTHING;
