\set ON_ERROR_STOP on

BEGIN;

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
GROUP BY day, group_id, device_id;

INSERT INTO schema_migrations(version) VALUES ('003_postgresql_portability')
ON CONFLICT (version) DO NOTHING;

COMMIT;
