\set ON_ERROR_STOP on

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
