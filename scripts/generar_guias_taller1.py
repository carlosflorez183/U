"""Genera las guias Word del Taller 1 Corte 2 en docs/guias/.

Salidas:
  GUIA_1_SUPABASE_TIMESCALE.docx  Base de datos en la nube con TimescaleDB
  GUIA_2_RENDER.docx              Publicacion de la API en Render
  GUIA_3_KNIME.docx               Analisis de datos y dashboard en KNIME
  GUIA_4_FLOWISE.docx             Agente de IA en FlowiseAI (+10 preguntas)
  TABLA_MENU_CONCEPTOS.docx       Relacion opcion del teclado -> concepto

Uso: python scripts/generar_guias_taller1.py
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.shared import Pt

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "docs" / "guias"


def _base_document() -> Document:
    document = Document()
    style = document.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)
    return document


def _code(document: Document, text: str) -> None:
    paragraph = document.add_paragraph()
    run = paragraph.add_run(text)
    run.font.name = "Consolas"
    run.font.size = Pt(9)


def _steps(document: Document, steps: list[str]) -> None:
    for step in steps:
        document.add_paragraph(step, style="List Number")


def _bullets(document: Document, items: list[str]) -> None:
    for item in items:
        document.add_paragraph(item, style="List Bullet")


def _table(document: Document, headers: list[str], rows: list[list[str]]) -> None:
    table = document.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = "Table Grid"
    for index, header in enumerate(headers):
        table.rows[0].cells[index].text = header
    for row_index, row in enumerate(rows, start=1):
        for col_index, value in enumerate(row):
            table.rows[row_index].cells[col_index].text = value


def guia_neon() -> None:
    document = _base_document()
    document.add_heading("Guía 1: Base de datos en la nube (Neon + TimescaleDB)", 0)
    document.add_paragraph(
        "Objetivo: crear PostgreSQL con la extensión TimescaleDB en la nube y "
        "cargar el esquema completo del proyecto (más de 10 tablas y una hypertable)."
    )

    document.add_heading("Paso 1: Crear la cuenta", 1)
    _steps(document, [
        "Entra a https://neon.com y haz clic en Sign up (puedes usar GitHub o correo).",
        "Confirma tu correo y entra al panel (Console).",
    ])
    document.add_paragraph(
        "Nota: Supabase ya no permite TimescaleDB en sus proyectos nuevos "
        "(PostgreSQL 17), por eso usamos Neon, que sí la tiene disponible gratis."
    )

    document.add_heading("Paso 2: Crear el proyecto", 1)
    _steps(document, [
        "Haz clic en New Project.",
        "Name: estacion-climatica (o el que prefieras).",
        "Postgres version: elige 17 (también funciona 16 o 18).",
        "Region: la más cercana a ti.",
        "Haz clic en Create Project. Neon crea la base de datos 'neondb' en segundos.",
    ])

    document.add_heading("Paso 3: Cargar el esquema del proyecto", 1)
    _steps(document, [
        "En el menú izquierdo entra a SQL Editor y haz clic en New Query.",
        "Abre el archivo docs/neon_instalacion.sql de tu proyecto, cópialo entero "
        "y pégalo en el editor.",
        "Haz clic en Run. Debes ver 'Success' (o el conteo final sin errores).",
    ])
    document.add_paragraph(
        "Ese archivo ejecuta en orden las migraciones 001 a 005: crea las tablas, "
        "los tipos de sensor DHT22 (temperatura y humedad), habilita TimescaleDB y "
        "convierte sensor_measurements en una hypertable con chunks de 1 día."
    )

    document.add_heading("Paso 4: Verificar (evidencias para el informe)", 1)
    document.add_paragraph("En el mismo SQL Editor, ejecuta estas consultas y toma captura de cada una:")
    _code(document, "-- 1) Extensión activa\nSELECT extname FROM pg_extension WHERE extname = 'timescaledb';")
    _code(document, "-- 2) Hypertable creada\nSELECT hypertable_name FROM timescaledb_information.hypertables;")
    _code(document, "-- 3) Chunks creados (evidencia pedida por el taller)\n"
                     "SELECT chunk_name, range_start, range_end\n"
                     "FROM timescaledb_information.chunks\n"
                     "WHERE hypertable_name = 'sensor_measurements'\n"
                     "ORDER BY range_start DESC\n"
                     "LIMIT 5;")
    _code(document, "-- 4) Conteo de tablas (debe ser 12 o más)\n"
                     "SELECT count(*) AS tablas\n"
                     "FROM information_schema.tables\n"
                     "WHERE table_schema = 'public' AND table_type = 'BASE TABLE';")

    document.add_heading("Paso 5: Copiar la cadena de conexión", 1)
    _steps(document, [
        "En el panel del proyecto haz clic en Connect (o en el botón Connection string).",
        "Copia la cadena 'Connection string'. Se verá algo como:\n"
        "postgresql://neondb_owner:PASSWORD@ep-xxx-xx.us-east-1.aws.neon.tech/neondb?sslmode=require",
        "Pega la cadena en tu bloc de notas. Es la que usarás en Render (Guía 2) y en KNIME (Guía 3).",
    ])
    document.add_paragraph(
        "Advertencia: esta cadena es privada. No la subas a GitHub ni la compartas."
    )

    document.add_heading("Justificación del intervalo de chunk (para el informe)", 1)
    document.add_paragraph(
        "Con el DHT22 enviando una lectura cada 20 segundos: 3 lecturas por minuto, "
        "180 por hora y 4.320 por día. Cada lectura guarda 2 filas en "
        "sensor_measurements (una de temperatura y una de humedad), es decir 8.640 "
        "filas por dispositivo al día. Un chunk_time_interval de 1 día agrupa "
        "aproximadamente 8.640 filas: es un fragmento lo bastante grande para no "
        "generar una cantidad excesiva de fragmentos diminutos y lo bastante "
        "pequeño para que las consultas de últimas horas o de hoy solo lean uno "
        "o dos chunks (podas por tiempo)."
    )

    document.add_heading("Errores comunes", 1)
    _bullets(document, [
        "Olvidar la contraseña de la base de datos: guarda la cadena de conexión al crearla.",
        "Pegar solo parte del SQL: el archivo completo debe ejecutarse de una sola vez.",
        "Intentar con Supabase: sus proyectos nuevos no tienen TimescaleDB; usa Neon.",
    ])
    documento_viejo = OUTPUT_DIR / "GUIA_1_SUPABASE_TIMESCALE.docx"
    if documento_viejo.exists():
        documento_viejo.unlink()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    document.save(OUTPUT_DIR / "GUIA_1_NEON_TIMESCALE.docx")


def guia_render() -> None:
    document = _base_document()
    document.add_heading("Guía 2: Publicar la API en Render (internet)", 0)
    document.add_paragraph(
        "Objetivo: dejar la API de FastAPI corriendo 24/7 en Render, conectada a la "
        "base de datos de Neon, con una URL pública tipo onrender.com."
    )

    document.add_heading("Paso 1: Subir el proyecto a GitHub", 1)
    _steps(document, [
        "Entra a https://github.com y crea un repositorio nuevo (puede ser privado), "
        "por ejemplo: api-estacion-climatica. NO inicialices con README.",
        "Abre una terminal (PowerShell) en la carpeta del proyecto U\\U y ejecuta:",
    ])
    _code(document,
          "git remote add origin https://github.com/TU-USUARIO/api-estacion-climatica.git\n"
          "git branch -M main\n"
          "git push -u origin main")
    document.add_paragraph(
        "El archivo .env (con contraseñas locales) está en .gitignore y NO se sube. "
        "Las contraseñas de producción se configuran directamente en Render."
    )

    document.add_heading("Paso 2: Crear el servicio en Render", 1)
    _steps(document, [
        "Entra a https://render.com con tu cuenta de GitHub.",
        "Haz clic en New → Blueprint y conecta tu cuenta de GitHub.",
        "Selecciona el repositorio api-estacion-climatica.",
        "Render detecta automáticamente el archivo render.yaml del proyecto; "
        "revisa que aparezca el servicio api-estacion-climatica y haz clic en Apply.",
    ])

    document.add_heading("Paso 3: Configurar la variable DATABASE_URL", 1)
    _steps(document, [
        "Antes del deploy, en la tarjeta del servicio entra a Environment.",
        "En DATABASE_URL pega la cadena de conexión de Neon (Guía 1, Paso 5).",
        "Las demás variables (ADMIN_API_KEY, ADMIN_SECRET_KEY, CREDENTIAL_PEPPER) "
        "ya se generan solas con valores aleatorios seguros.",
        "Copia esos tres valores generados a tu bloc de notas: los necesitarás para "
        "registrar el dispositivo (Paso 5). Se ven en Environment → clic en el ojo.",
    ])

    document.add_heading("Paso 4: Desplegar", 1)
    _steps(document, [
        "Haz clic en Deploy (o Apply). Sigue la pestaña Logs: se instalan las "
        "librerías y arranca uvicorn.",
        "Cuando el estado pase a Live, Render muestra la URL pública, por ejemplo:\nhttps://api-estacion-climatica-xxxx.onrender.com",
        "Abre https://TU-URL/docs y verás el Swagger UI de FastAPI.",
        "Abre https://TU-URL/health/ready y debe responder {\"status\": \"ready\"}.",
    ])
    document.add_paragraph(
        "Nota: en el plan gratuito el servicio se duerme tras un rato sin uso; la "
        "primera petición tarda unos segundos extra (cold start). No es un error."
    )

    document.add_heading("Paso 5: Registrar el dispositivo y su credencial", 1)
    document.add_paragraph(
        "Con PowerShell (o con el propio Swagger en /docs), ejecuta usando los "
        "valores ADMIN_API_KEY y ADMIN_SECRET_KEY de Render:"
    )
    _code(document,
          "$admin = @{ \"X-Admin-API-Key\" = \"TU_ADMIN_API_KEY\"; \"X-Admin-Secret-Key\" = \"TU_ADMIN_SECRET_KEY\" }\n"
          "$body = @{ group_id = \"grupo-01\"; device_id = \"esp32-grupo-01\"; alias = \"ESP32 DHT22\" } | ConvertTo-Json\n"
          "Invoke-RestMethod -Method Post -Uri \"https://TU-URL/api/v2/admin/devices\" -Headers $admin -Body $body -ContentType \"application/json\"\n"
          "\n"
          "$cred = @{ device_id = \"esp32-grupo-01\"; alias = \"wokwi-final\" } | ConvertTo-Json\n"
          "Invoke-RestMethod -Method Post -Uri \"https://TU-URL/api/v2/admin/credentials\" -Headers $admin -Body $cred -ContentType \"application/json\"")
    document.add_paragraph(
        "La respuesta de credentials trae api_key y secret_key una sola vez: "
        "cópialas al firmware (son las que el ESP32 envía en X-API-Key / X-Secret-Key)."
    )

    document.add_heading("Paso 6: Apuntar el firmware a la nube", 1)
    _steps(document, [
        "Abre firmware/esp32_agro_iot/esp32_agro_iot.ino (o el proyecto Wokwi humedad).",
        "Cambia API_HOST por tu URL de Render, sin barra al final:\nconst char* API_HOST = \"https://api-estacion-climatica-xxxx.onrender.com\";",
        "Cambia API_KEY y SECRET_KEY por las recién creadas.",
        "Vuelve a simular en Wokwi o a cargar el ESP32: debe responder HTTP 201.",
    ])
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    document.save(OUTPUT_DIR / "GUIA_2_RENDER.docx")


def guia_knime() -> None:
    document = _base_document()
    document.add_heading("Guía 3: Análisis de datos y dashboard en KNIME", 0)
    document.add_paragraph(
        "Objetivo: conectar KNIME a PostgreSQL (Neon), limpiar y analizar las "
        "lecturas del DHT22, exportar un CSV limpio y armar un dashboard."
    )

    document.add_heading("Paso 0: Instalar KNIME", 1)
    _steps(document, [
        "Entra a https://www.knime.com/download y descarga KNIME Analytics Platform (gratis).",
        "Instala y abre. Crea un proyecto nuevo: File → New KNIME Workflow.",
    ])

    document.add_heading("Paso 1: Conexión a PostgreSQL (sin archivos intermedios)", 1)
    _steps(document, [
        "En Node Repository busca 'DB Connector' y arrástralo al lienzo.",
        "Doble clic: Host = ep-xxxx.us-east-1.aws.neon.tech (de tu cadena de "
        "conexión), Database = neondb, puerto 5432, usuario neondb_owner, "
        "password = el de tu proyecto.",
        "En la pestaña Settings activa 'Use SSL'. OK.",
        "Añade 'DB Table Selector' y elige la vista vw_telemetry_wide (todas las "
        "lecturas con temperatura, humedad y estados). Ejecuta con F7.",
    ])
    document.add_paragraph(
        "Alternativa sin base de datos: usa el archivo datasets/dataset_dht22.csv "
        "con un nodo CSV Reader. Pero el taller pide conexión directa a PostgreSQL."
    )

    document.add_heading("Paso 2: Unir tablas (Joiner)", 1)
    _steps(document, [
        "Añade otro 'DB Table Selector' con vw_daily_stats (resumen diario).",
        "Conecta ambos selectores a un nodo 'Joiner' (unir por device_id) si "
        "quieres enriquecer las lecturas con sus estadísticos del día.",
    ])

    document.add_heading("Paso 3: Exploración", 1)
    _bullets(document, [
        "Statistics: medias, medianas, desviaciones de temperatura y humedad.",
        "Distribution Calculation: histogramas de temperatura.",
        "Correlation Matrix: relación entre temperatura y humedad (suele ser negativa).",
    ])

    document.add_heading("Paso 4: Limpieza", 1)
    _steps(document, [
        "String to Number sobre temperature_celsius y humidity_percent "
        "(corrige valores como \"25,3\" con coma).",
        "Missing Value: elimina o imputa las filas con humedad vacía (~40 filas).",
        "Duplicate Row Filter: elimina las lecturas duplicadas (~15 filas).",
        "Row Filter / Rule-based Row Filter: marca valores atípicos "
        "(temperatura fuera de 0–45 °C o humedad fuera de 5–100 %).",
    ])

    document.add_heading("Paso 5: Transformación", 1)
    _bullets(document, [
        "Date&Time Fields: extraer Hora y Día desde measured_at.",
        "GroupBy: promedios y máximos por hora y por día.",
        "Math Formula o Rolling Statistics: promedios móviles de 30 minutos.",
        "String Manipulation: categorías (Frío / Confortable / Caliente).",
    ])

    document.add_heading("Paso 6: Análisis (conceptos de los talleres anteriores)", 1)
    _bullets(document, [
        "Medidas de tendencia central: media, mediana, moda de temperatura y humedad.",
        "Medidas de dispersión: rango, varianza, desviación estándar, percentiles.",
        "Correlación entre temperatura y humedad.",
        "Comparación de días y de franjas horarias (máx/min del día).",
    ])

    document.add_heading("Paso 7: Exportar dataset limpio", 1)
    _steps(document, [
        "Añade el nodo 'CSV Writer' al final de la limpieza.",
        "Ruta de salida: por ejemplo C:\\Users\\TU-USER\\Documents\\dataset_dht22_limpio.csv.",
        "Ejecuta el flujo completo con Execute All (F7).",
    ])
    document.add_paragraph(
        "Ese CSV limpio es un entregable del Componente 3 y también la fuente "
        "del agente de Flowise (Componente 4)."
    )

    document.add_heading("Paso 8: Dashboard interactivo", 1)
    _steps(document, [
        "Añade nodos de vista: Line Plot (serie de temperatura), "
        "Bar Chart (promedio por hora), Pie Chart (distribución de estados), "
        "Box Plot (dispersión por día).",
        "Conéctalos todos a un nodo 'View' o deja los gráficos en el lienzo.",
        "Publica: File → Export → KNIME Workflow (.knwf) para entregar el archivo "
        "y, para el dashboard interactivo, usa View → Open View en cada gráfico "
        "durante la sustentación (o publica en KNIME Community Hub si lo deseas).",
    ])

    document.add_heading("Documentación del workflow", 1)
    document.add_paragraph(
        "El taller exige un .knwf con anotaciones. En KNIME haz doble clic en el "
        "lienzo vacío para añadir notas (annotations) explicando cada bloque: "
        "Conexión, Exploración, Limpieza, Transformación y Dashboard. "
        "Luego exporta con File → Export → KNIME Workflow (.knwf)."
    )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    document.save(OUTPUT_DIR / "GUIA_3_KNIME.docx")


def guia_flowise() -> None:
    document = _base_document()
    document.add_heading("Guía 4: Agente de IA en FlowiseAI", 0)
    document.add_paragraph(
        "Objetivo: crear un agente que responda preguntas sobre las lecturas del "
        "DHT22 (dataset con más de 8.600 registros), siguiendo la práctica del "
        "documento 'Creación de un Agente de inteligencia artificial'."
    )

    document.add_heading("Paso 1: Las tres credenciales (cuentas gratuitas)", 1)
    _bullets(document, [
        "Qdrant (la memoria): entra a https://qdrant.tech, crea cuenta, crea un "
        "cluster gratuito y copia la API Key y la URL del clúster.",
        "HuggingFace (el traductor a números): entra a https://huggingface.co, "
        "Settings → Access Tokens → New token (permiso Read) y cópialo.",
        "Groq (el cerebro): entra a https://console.groq.com, API Keys → Create "
        "API Key y cópiala.",
    ])
    document.add_paragraph("Guarda las tres claves en tu bloc de notas; no las compartas.")

    document.add_heading("Paso 2: Preparar el dataset", 1)
    document.add_paragraph(
        "Usa el archivo datasets/dataset_dht22.csv del proyecto: tiene 8.655 "
        "lecturas del DHT22 cada 20 segundos durante 2 días (supera las 3.000 "
        "registros que pide el taller). También puedes usar el CSV limpio que "
        "exportaste desde KNIME."
    )

    document.add_heading("Paso 3: Construir el agente en FlowiseAI", 1)
    _steps(document, [
        "Entra a https://flowiseai.com y crea tu cuenta.",
        "En el panel, crea un flujo nuevo tipo Agentflow (como en la práctica).",
        "Sube el archivo dataset_dht22.csv como documento/knowledge y haz clic en "
        "Process.",
        "En la configuración de embebido (embedding) elige HuggingFace y pega tu token.",
        "En la configuración del almacén vectorial (Vector Store) elige Qdrant y "
        "pega la API Key y la URL del clúster.",
        "Añade un nodo Agente (+ → Agent) y conecta Start → Agente.",
        "Doble clic al Agente: proveedor Groq, pega la API Key y elige un modelo "
        "como llama3-8b-8192 o mixtral-8x7b-32768.",
        "Instrucción del sistema (system prompt), copia y pega:",
    ])
    _code(document,
          "Eres el asistente de la estacion climatica DHT22 del grupo-01. Respondes "
          "unicamente con informacion del dataset de lecturas (temperatura y humedad "
          "cada 20 segundos, 2 dias, hora UTC). Si te preguntan algo fuera del "
          "dataset, dilo claramente. Da respuestas cortas con los numeros exactos "
          "y menciona la fecha u hora a la que se refieren.")
    _steps(document, [
        "Guarda el flujo y pruébalo en el chat integrado.",
    ])

    document.add_heading("Paso 4: Los tres modos", 1)
    _table(document, ["Modo", "Cómo mostrarlo"], [
        ["Agente", "Abre el flujo Agentflow y muestra la configuración de nodos."],
        ["Chat", "Habilita el chat del flujo y conversa en vivo."],
        ["Aplicativo web", "En Share/Embed del flujo copia el enlace o el código "
                           "iframe y ábrelo en el navegador."],
    ])

    document.add_heading("Paso 5: 10 preguntas de prueba con respuestas", 1)
    document.add_paragraph(
        "El taller pide verificar las respuestas. Estas son las respuestas "
        "calculadas directamente del dataset (pequeñas diferencias de redondeo "
        "son normales):"
    )
    _table(document, ["#", "Pregunta", "Respuesta verificada"], [
        ["1", "¿Cuántas lecturas tiene el dataset?", "8.655 filas"],
        ["2", "¿Cuál es la temperatura promedio general?", "≈ 23,0 °C"],
        ["3", "¿Cuál es la temperatura máxima registrada?", "41,0 °C (valor atípico)"],
        ["4", "¿Cuál es la humedad promedio?", "≈ 62,1 %"],
        ["5", "¿A qué hora del día es más caluroso (promedio)?", "≈ 16:00 UTC (28,5 °C)"],
        ["6", "¿A qué hora es más fresco (promedio)?", "≈ 04:00 UTC (17,5 °C)"],
        ["7", "¿Qué % de lecturas está en zona de confort (18–28 °C)?", "≈ 76,8 %"],
        ["8", "¿Cuántas lecturas tienen la humedad vacía?", "40 filas"],
        ["9", "Comparando el 16 y el 17 de octubre, ¿hubo tendencia al alza?", "No; ambos días promedian ≈ 23,0 °C (estable)"],
        ["10", "¿Cuál es la desviación estándar de la temperatura?", "≈ 3,9 °C"],
    ])
    document.add_paragraph(
        "Presenta el agente en los tres modos y deja estas preguntas a la vista; "
        "el docente puede plantear preguntas nuevas (por ejemplo: ¿cuál fue la "
        "humedad a las 10:00 del 17?)."
    )
    document.add_heading("Seguridad", 1)
    document.add_paragraph(
        "Nunca subas tus claves de Qdrant, HuggingFace o Groq a GitHub ni a "
        "capturas que vayas a compartir; regeneralas si se filtran."
    )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    document.save(OUTPUT_DIR / "GUIA_4_FLOWISE.docx")


def tabla_menu_conceptos() -> None:
    document = _base_document()
    document.add_heading("Tabla: opciones del teclado matricial y concepto de analítica", 0)
    document.add_paragraph(
        "Entregable del Componente 2: relación entre cada tecla del menú y el "
        "concepto de analítica que aplica, con el endpoint de la API que la respalda."
    )
    _table(document, ["Tecla", "Opción del menú", "Concepto de analítica", "Endpoint"], [
        ["1", "Valor actual de cada sensor", "Lectura en tiempo real / última observación", "/api/v2/menu/realtime"],
        ["2", "Promedio de la última hora", "Medida de tendencia central (media muestral)", "/api/v2/menu/hourly-average"],
        ["3", "Máximo y mínimo del día", "Valores extremos y rango", "/api/v2/menu/daily-extremes"],
        ["4", "Desviación estándar y tendencia", "Dispersión y comparación entre periodos", "/api/v2/menu/trend"],
        ["5", "Detección de valores atípicos", "Outliers: más de 2σ del promedio diario", "/api/v2/menu/outliers"],
        ["6", "Conteo de alertas activas", "Reglas de negocio (confort) y calidad del dato", "/api/v2/menu/alerts"],
        ["7", "Estado de conexión a la nube", "Disponibilidad / last_seen del dispositivo", "/api/v2/menu/connection"],
        ["*", "Volver a la pantalla en vivo", "Navegación del menú", "—"],
        ["#", "Actualizar opción seleccionada", "Refresco de la consulta", "—"],
    ])
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    document.save(OUTPUT_DIR / "TABLA_MENU_CONCEPTOS.docx")


def main() -> None:
    guia_neon()
    guia_render()
    guia_knime()
    guia_flowise()
    tabla_menu_conceptos()
    print("Guias generadas en", OUTPUT_DIR)
    for path in sorted(OUTPUT_DIR.glob("*.docx")):
        print(" -", path.name)


if __name__ == "__main__":
    main()
