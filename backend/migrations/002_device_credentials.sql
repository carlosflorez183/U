\set ON_ERROR_STOP on

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
) rain ON TRUE;

INSERT INTO schema_migrations(version) VALUES ('002_device_credentials')
ON CONFLICT (version) DO NOTHING;

COMMIT;
