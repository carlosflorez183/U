-- Plantilla opcional para despliegue. Sustituye la contraseña antes de ejecutar.
CREATE ROLE powerbi_reader LOGIN PASSWORD 'CAMBIAR-CONTRASENA-FUERTE';
GRANT CONNECT ON DATABASE agro_iot TO powerbi_reader;
GRANT USAGE ON SCHEMA public TO powerbi_reader;
GRANT SELECT ON vw_telemetry_wide, vw_powerbi_daily_summary TO powerbi_reader;
