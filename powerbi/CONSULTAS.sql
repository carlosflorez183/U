-- Fuentes directas preparadas para Power BI.
SELECT *
FROM vw_telemetry_wide;

SELECT *
FROM vw_powerbi_daily_summary;

-- Comprobación de frescura.
SELECT
    COUNT(*) AS total_samples,
    MAX(measured_at) AS last_measurement
FROM vw_telemetry_wide;
