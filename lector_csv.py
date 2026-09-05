"""
Lector de CSV con análisis exploratorio básico.

Basado en:
  - "Limpieza basica"                -> etapas de limpieza de datos
  - "TEMA 3 ANALISIS EXPLORATORIO"   -> info(), frecuencia absoluta/relativa,
                                        gráficos y tablas de contingencia
  - "MINERIA_STREAMLIT"              -> Streamlit como interfaz web

Ejecutar:
    streamlit run lector_csv.py
"""

import io
import unicodedata

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

# --------------------------------------------------------------------------- #
# Configuración general
# --------------------------------------------------------------------------- #

st.set_page_config(page_title="Lector de CSV", page_icon="📄", layout="wide")

# Separadores que se prueban cuando el usuario elige "Automático".
CANDIDATOS_SEP = [",", ";", "\t", "|"]

# Codificaciones más comunes en archivos de entidades colombianas.
CANDIDATOS_ENCODING = ["utf-8-sig", "utf-8", "latin-1", "cp1252"]

# Nombres legibles para los separadores (un tabulador no se ve en un selectbox).
ETIQUETAS_SEP = {
    "Automático": None,
    "Coma  ,": ",",
    "Punto y coma  ;": ";",
    "Tabulador  \\t": "\t",
    "Barra vertical  |": "|",
}


# --------------------------------------------------------------------------- #
# Lectura del CSV
# --------------------------------------------------------------------------- #


def _leer(contenido: bytes, sep: str, encoding: str, decimal: str, miles: str) -> pd.DataFrame:
    """Lee el CSV con una combinación concreta de separador y codificación."""
    return pd.read_csv(
        io.BytesIO(contenido),
        sep=sep,
        encoding=encoding,
        decimal=decimal,
        # thousands="" no es válido en pandas: hay que pasar None.
        thousands=miles or None,
        # skipinitialspace limpia los espacios que quedan tras el separador.
        skipinitialspace=True,
    )


def _detectar_separador(contenido: bytes, encoding: str, decimal: str, miles: str) -> str:
    """
    Elige el separador que produce más columnas.

    Es una heurística simple pero fiable: si el archivo usa ';' y lo leemos con
    ',', pandas devuelve una sola columna con todo el texto pegado.
    """
    mejor_sep, mejor_columnas = CANDIDATOS_SEP[0], 0
    for sep in CANDIDATOS_SEP:
        try:
            # nrows=50 basta para contar columnas y evita leer archivos enteros.
            muestra = pd.read_csv(
                io.BytesIO(contenido),
                sep=sep,
                encoding=encoding,
                nrows=50,
                skipinitialspace=True,
            )
        except Exception:
            continue
        if muestra.shape[1] > mejor_columnas:
            mejor_sep, mejor_columnas = sep, muestra.shape[1]
    return mejor_sep


@st.cache_data(show_spinner="Leyendo el archivo...")
def cargar_csv(contenido: bytes, sep_elegido, encoding_elegido, decimal: str, miles: str):
    """
    Devuelve (df, encoding_usado, separador_usado).

    Recibe `bytes` en lugar del objeto subido para que `st.cache_data` pueda
    usar el contenido como clave de caché: así no se relee en cada interacción.
    """
    encodings = [encoding_elegido] if encoding_elegido else CANDIDATOS_ENCODING
    errores = []

    for encoding in encodings:
        sep = sep_elegido or _detectar_separador(contenido, encoding, decimal, miles)
        try:
            df = _leer(contenido, sep, encoding, decimal, miles)
        except Exception as exc:
            errores.append(f"- `{encoding}` con separador `{sep!r}`: {exc}")
            continue
        if df.empty and df.shape[1] == 0:
            errores.append(f"- `{encoding}` con separador `{sep!r}`: archivo vacío")
            continue
        return df, encoding, sep

    raise ValueError("No se pudo leer el CSV.\n" + "\n".join(errores))


# --------------------------------------------------------------------------- #
# Limpieza básica (etapas del documento "Limpieza basica")
# --------------------------------------------------------------------------- #


def normalizar_nombre(nombre: str) -> str:
    """`Área de Residencia ` -> `area_de_residencia` (sin tildes ni espacios)."""
    texto = str(nombre).strip().lower()
    # NFKD separa la letra de su acento y luego descartamos los acentos.
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    for viejo, nuevo in ((" ", "_"), ("-", "_"), (".", ""), ("/", "_")):
        texto = texto.replace(viejo, nuevo)
    while "__" in texto:
        texto = texto.replace("__", "_")
    return texto.strip("_")


def columnas_texto(df: pd.DataFrame) -> list[str]:
    """
    Columnas no numéricas y no de fecha.

    Se evita `select_dtypes(include="object")` porque desde pandas 3.0 las
    cadenas usan el dtype `str`, no `object`, y quedarían fuera.
    """
    return [
        col
        for col in df.columns
        if not pd.api.types.is_numeric_dtype(df[col])
        and not pd.api.types.is_datetime64_any_dtype(df[col])
    ]


def candidatas_categoricas(df: pd.DataFrame, max_unicos: int = 30) -> list[str]:
    """
    Columnas que tiene sentido tratar como categoría.

    Incluye las numéricas con pocos valores distintos, porque como advierte el
    material del curso una variable categórica puede contener números
    (por ejemplo un código de estrato o de comuna).
    """
    categoricas = columnas_texto(df)
    numericas_discretas = [
        col
        for col in df.columns
        if col not in categoricas and df[col].nunique(dropna=True) <= max_unicos
    ]
    return categoricas + numericas_discretas


def aplicar_limpieza(df: pd.DataFrame, renombrar: bool, recortar: bool, sin_duplicados: bool):
    """Aplica la limpieza opcional y devuelve (df, lista de cambios)."""
    df = df.copy()
    cambios = []

    if renombrar:
        nuevos = {col: normalizar_nombre(col) for col in df.columns}
        modificadas = sum(1 for viejo, nuevo in nuevos.items() if viejo != nuevo)
        df = df.rename(columns=nuevos)
        cambios.append(f"Nombres de columna normalizados: {modificadas}")

    if recortar:
        for col in columnas_texto(df):
            # astype("string") garantiza el accesor .str y conserva los nulos.
            df[col] = df[col].astype("string").str.strip()
        cambios.append(f"Espacios recortados en {len(columnas_texto(df))} columnas de texto")

    if sin_duplicados:
        antes = len(df)
        df = df.drop_duplicates()
        cambios.append(f"Filas duplicadas eliminadas: {antes - len(df)}")

    return df, cambios


# --------------------------------------------------------------------------- #
# Panel lateral: origen de los datos y opciones de lectura
# --------------------------------------------------------------------------- #

st.sidebar.header("1. Archivo")

archivo = st.sidebar.file_uploader("Selecciona un CSV", type=["csv", "txt"])
ruta = st.sidebar.text_input(
    "...o escribe una ruta local",
    placeholder="ejemplo_nacidos_vivos.csv",
    help="Se usa solo si no subes un archivo.",
)

st.sidebar.header("2. Opciones de lectura")

sep_elegido = ETIQUETAS_SEP[st.sidebar.selectbox("Separador", list(ETIQUETAS_SEP))]
encoding_etiqueta = st.sidebar.selectbox("Codificación", ["Automático"] + CANDIDATOS_ENCODING)
encoding_elegido = None if encoding_etiqueta == "Automático" else encoding_etiqueta
decimal = st.sidebar.selectbox("Separador decimal", [".", ","])
miles = st.sidebar.selectbox("Separador de miles", ["(ninguno)", ",", ".", " "])
miles = "" if miles == "(ninguno)" else miles

st.sidebar.header("3. Limpieza básica")

opt_renombrar = st.sidebar.checkbox("Normalizar nombres de columnas", value=False)
opt_recortar = st.sidebar.checkbox("Recortar espacios en textos", value=False)
opt_duplicados = st.sidebar.checkbox("Eliminar filas duplicadas", value=False)


# --------------------------------------------------------------------------- #
# Carga
# --------------------------------------------------------------------------- #

st.title("📄 Lector de CSV")

if archivo is not None:
    contenido = archivo.getvalue()
    origen = archivo.name
elif ruta.strip():
    try:
        with open(ruta.strip(), "rb") as f:
            contenido = f.read()
        origen = ruta.strip()
    except OSError as exc:
        st.error(f"No se pudo abrir la ruta indicada: {exc}")
        st.stop()
else:
    st.info("Sube un CSV o escribe una ruta en el panel lateral para comenzar.")
    st.stop()

try:
    df_original, encoding_usado, sep_usado = cargar_csv(
        contenido, sep_elegido, encoding_elegido, decimal, miles
    )
except ValueError as exc:
    st.error(str(exc))
    st.stop()

df, cambios = aplicar_limpieza(df_original, opt_renombrar, opt_recortar, opt_duplicados)

# Verificar que el cargue fue exitoso (TEMA 3, diapositiva 4).
st.success(
    f"Archivo **{origen}** leído correctamente: "
    f"{len(df):,} filas × {df.shape[1]} columnas · "
    f"codificación `{encoding_usado}` · separador `{sep_usado!r}`"
)
for cambio in cambios:
    st.caption(f"• {cambio}")


# --------------------------------------------------------------------------- #
# Pestañas de análisis
# --------------------------------------------------------------------------- #

tab_datos, tab_estructura, tab_calidad, tab_frec, tab_conting = st.tabs(
    ["Datos", "Estructura", "Calidad", "Frecuencias", "Tabla de contingencia"]
)

# --- Datos ----------------------------------------------------------------- #
with tab_datos:
    # st.slider exige min < max, así que con archivos muy cortos no se dibuja.
    tope_filas = min(200, len(df))
    if tope_filas > 5:
        n = st.slider("Filas a mostrar", 5, tope_filas, min(20, tope_filas))
    else:
        n = tope_filas
        st.caption(f"El archivo tiene {len(df)} filas: se muestran todas.")

    posicion = st.radio("Desde", ["Inicio", "Final", "Muestra aleatoria"], horizontal=True)

    if posicion == "Inicio":
        vista = df.head(n)
    elif posicion == "Final":
        vista = df.tail(n)
    else:
        # La verificación final del documento de limpieza pide revisar una
        # muestra aleatoria de filas.
        vista = df.sample(min(n, len(df)), random_state=42)

    st.dataframe(vista, width="stretch")

    st.download_button(
        "Descargar datos procesados (CSV)",
        df.to_csv(index=False).encode("utf-8"),
        file_name="datos_procesados.csv",
        mime="text/csv",
    )

# --- Estructura ------------------------------------------------------------ #
with tab_estructura:
    c1, c2, c3 = st.columns(3)
    c1.metric("Filas", f"{len(df):,}")
    c2.metric("Columnas", df.shape[1])
    c3.metric("Memoria", f"{df.memory_usage(deep=True).sum() / 1_048_576:.2f} MB")

    st.subheader("df.info()")
    buffer = io.StringIO()
    df.info(buf=buffer)
    st.code(buffer.getvalue(), language="text")

    st.subheader("Tipos de dato por columna")
    resumen = pd.DataFrame(
        {
            "tipo": df.dtypes.astype(str),
            "no_nulos": df.notna().sum(),
            "nulos": df.isna().sum(),
            "valores_unicos": df.nunique(dropna=True),
        }
    )
    st.dataframe(resumen, width="stretch")

# --- Calidad --------------------------------------------------------------- #
with tab_calidad:
    st.subheader("Valores faltantes")
    faltantes = pd.DataFrame(
        {
            "nulos": df.isna().sum(),
            "porcentaje": (df.isna().mean() * 100).round(2),
        }
    ).sort_values("nulos", ascending=False)
    st.dataframe(faltantes, width="stretch")

    st.subheader("Duplicados")
    duplicadas = int(df.duplicated().sum())
    st.metric("Filas duplicadas", f"{duplicadas:,}")
    if duplicadas:
        st.dataframe(df[df.duplicated(keep=False)].head(50), width="stretch")
        st.caption("Activa 'Eliminar filas duplicadas' en el panel lateral para quitarlas.")

    numericas = df.select_dtypes(include="number")
    if not numericas.empty:
        st.subheader("Estadísticas descriptivas (numéricas)")
        st.dataframe(numericas.describe().T, width="stretch")

        st.subheader("Diagrama de caja y bigotes")
        col_caja = st.selectbox("Columna numérica", numericas.columns, key="caja")
        fig, ax = plt.subplots(figsize=(7, 2.5))
        # Un boxplot muestra los cuartiles y deja ver los outliers como puntos.
        serie = numericas[col_caja].dropna()
        try:
            ax.boxplot(serie, orientation="horizontal")  # matplotlib >= 3.11
        except TypeError:
            ax.boxplot(serie, vert=False)  # matplotlib < 3.11
        ax.set_xlabel(col_caja)
        st.pyplot(fig)
        plt.close(fig)

# --- Frecuencias ----------------------------------------------------------- #
with tab_frec:
    candidatas = candidatas_categoricas(df)
    if not candidatas:
        st.info("No se detectaron columnas categóricas en este archivo.")
    else:
        col = st.selectbox("Variable categórica", candidatas, key="frecuencia")

        absoluta = df[col].value_counts(dropna=False)
        relativa = df[col].value_counts(normalize=True, dropna=False)

        tabla = pd.DataFrame(
            {
                "frecuencia_absoluta": absoluta,
                "frecuencia_relativa": relativa.round(4),
                "porcentaje": (relativa * 100).round(2),
            }
        )
        tabla.index.name = col
        st.dataframe(tabla, width="stretch")

        # Con 3 categorías o menos no hay nada que recortar y el slider sería inválido.
        if len(tabla) > 3:
            top = st.slider("Categorías a graficar", 3, min(20, len(tabla)), min(10, len(tabla)))
        else:
            top = len(tabla)
        datos_grafico = absoluta.head(top)

        g1, g2 = st.columns(2)
        with g1:
            st.caption("Frecuencia absoluta")
            fig, ax = plt.subplots(figsize=(6, 4))
            ax.bar(datos_grafico.index.astype(str), datos_grafico.values, color="#4C78A8")
            ax.set_ylabel("Cantidad de registros")
            ax.tick_params(axis="x", rotation=45)
            st.pyplot(fig)
            plt.close(fig)
        with g2:
            st.caption("Distribución porcentual")
            fig, ax = plt.subplots(figsize=(6, 4))
            ax.pie(datos_grafico.values, labels=datos_grafico.index.astype(str), autopct="%1.1f%%")
            ax.axis("equal")
            st.pyplot(fig)
            plt.close(fig)

# --- Tabla de contingencia ------------------------------------------------- #
with tab_conting:
    candidatas = candidatas_categoricas(df)
    if len(candidatas) < 2:
        st.info("Se necesitan al menos dos columnas categóricas.")
    else:
        c1, c2 = st.columns(2)
        fila = c1.selectbox("Filas", candidatas, index=0, key="cont_fila")
        columna = c2.selectbox("Columnas", candidatas, index=1, key="cont_col")

        modo = st.radio(
            "Valores", ["Conteo", "% por fila", "% por columna", "% del total"], horizontal=True
        )
        normalizar = {
            "Conteo": False,
            "% por fila": "index",
            "% por columna": "columns",
            "% del total": "all",
        }[modo]

        cruce = pd.crosstab(df[fila], df[columna], normalize=normalizar)
        if normalizar:
            cruce = (cruce * 100).round(2)

        st.dataframe(cruce, width="stretch")

        st.caption(f"Análisis bivariado: {fila} vs {columna}")
        fig, ax = plt.subplots(figsize=(9, 4.5))
        cruce.head(15).plot(kind="bar", stacked=True, ax=ax)
        ax.set_ylabel("Porcentaje" if normalizar else "Cantidad")
        ax.legend(title=columna, bbox_to_anchor=(1.02, 1), loc="upper left")
        ax.grid(axis="y", alpha=0.3)
        st.pyplot(fig)
        plt.close(fig)
