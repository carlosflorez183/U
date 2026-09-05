# PARCIAL CORTE 1 70%

| Aspecto | Detalle |
| :--- | :--- |
| **Modalidad** | Trabajo en grupo (máximo 5 integrantes) |
| **Ponderación** | 70% del corte / parcial |
| **Tecnologías** | ESP32, PostgreSQL, Flask/FastAPI, Streamlit, Power BI |
| **Sustentación** | Se selecciona un integrante de cada equipo el cual será el único vocero para representar el equipo. |

---

## 1. Introducción
El presente parcial integrador tiene como propósito consolidar, de manera práctica y aplicada, las competencias desarrolladas a lo largo de la asignatura de Minería de Datos con énfasis en Analítica de Datos. A diferencia de una evaluación tradicional basada en preguntas teóricas, este ejercicio exige que cada grupo de estudiantes construya una solución tecnológica completa que abarque desde la captura física de datos mediante sensores conectados a un microcontrolador ESP32, hasta su almacenamiento estructurado, su análisis exploratorio y su visualización en tableros interactivos.

## 2. Contexto del problema
En la actualidad, el Internet de las Cosas (IoT) se ha convertido en una fuente masiva de datos en tiempo real para sectores como la agricultura, el ambiente, la industria y las ciudades inteligentes. Sin embargo, la sola captura de datos no genera valor por sí misma: el verdadero reto está en construir arquitecturas capaces de almacenar esos datos de forma confiable, analizarlos con rigor estadístico y comunicarlos de manera clara a través de dashboards que faciliten la interpretación por parte de tomadores de decisión.

## 3. Objetivo general
Diseñar, implementar y sustentar una solución integral de analítica de datos que permita capturar información real mediante sensores IoT conectados a un ESP32, almacenarla en una base de datos PostgreSQL a través de una API REST, analizarla mediante técnicas de minería de datos y analítica exploratoria en Streamlit, y visualizarla en un dashboard ejecutivo desarrollado en Power BI.

## 4. Objetivos específicos
* Implementar un circuito electrónico funcional con ESP32, dos sensores asignados y una pantalla LCD I2C que muestre las variables monitoreadas en tiempo real así como la comunicación con la API.
* Diseñar y desarrollar una API REST (Flask o FastAPI) capaz de recibir, validar y almacenar los datos enviados por el ESP32 en una base de datos PostgreSQL correctamente modelada.
* Aplicar técnicas de análisis exploratorio de datos (EDA) para describir el comportamiento, la distribución y la calidad de las variables capturadas.
* Construir una aplicación analítica interactiva en Streamlit que permita explorar, filtrar y visualizar los datos capturados. Así mismo realizar predicciones con dos modelos de Machine Learning.
* Elaborar un dashboard ejecutivo en Power BI conectado directamente a PostgreSQL, orientado a la toma de decisiones (similar al taller).
* Interpretar y comunicar los hallazgos obtenidos a partir de los datos reales recolectados, argumentando las conclusiones durante la sustentación.

## 5. Descripción de los grupos y sensores asignados
Con el fin de garantizar diversidad en los conjuntos de datos y en los análisis realizados, cada uno de los 5 grupos trabajará con una combinación distinta de dos sensores compatibles con ESP32, según la asignación del docente.

Todos los grupos, independientemente de la combinación de sensores, deberán integrar además:
* Un microcontrolador ESP32 como unidad central de procesamiento y comunicación.
* Una pantalla LCD I2C para visualización local de las variables capturadas.
* Conectividad WiFi para el envío de datos hacia la API REST.

## 6. Requerimientos
* El sistema debe capturar datos reales de dos sensores de forma periódica (frecuencia sugerida: cada 10 o 5 segundos).
* El ESP32 debe mostrar en la pantalla LCD I2C, en tiempo real, los valores actuales de las dos variables monitoreadas e indicar procesos como envío de los datos.
* El ESP32 debe transmitir los datos capturados a la API REST mediante solicitudes HTTP (POST) en formato JSON.
* La API que debe tener una estructura de POO con una distribución de carpetas y archivos, debe validar el tipo, rango y formato de los datos antes de almacenarlos.
* Los datos deben almacenarse en PostgreSQL usando la extensión **TIMESCALEDB** con marca de tiempo (timestamp) e identificación del grupo/dispositivo.
* La aplicación en Streamlit debe permitir explorar los datos históricos mediante filtros dinámicos de fecha, rango de valores y variable.
* El dashboard en Power BI debe conectarse directamente a la base de datos PostgreSQL, sin datos cargados manualmente.
* El sistema debe permitir identificar valores atípicos o anómalos en los datos capturados.

## 7. Requerimientos técnicos

### 7.1 Hardware
* Microcontrolador ESP32.
* Dos sensores asignados según el grupo correspondiente.
* Pantalla LCD I2C (16x2 o 20x4).
* Protoboard, cables de conexión y fuente de alimentación estable.
* **Nota:** debe seguir el procedimiento trabajado en sistemas de control con respecto al diseño del circuito electrónico (**usar cable UTP, no usar cables macho hembra, ni los vinculados en el kit de Arduino**).

### 7.2 Software y lenguajes
* Arduino IDE para la programación del ESP32 (lenguaje C/C++).
* Python 3.10 o superior.
* Flask o FastAPI para el desarrollo de la API REST.
* PostgreSQL como motor de base de datos relacional.
* Streamlit para la aplicación analítica interactiva.
* Power BI Desktop para el dashboard ejecutivo.
* Librerías de análisis de datos en Python: pandas, numpy, matplotlib/plotly, scipy.

## 8. Entregables
Cada grupo debe entregar los siguientes productos, organizados en un repositorio o carpeta compartida debidamente estructurada:

| Fase | Entregables |
| :--- | :--- |
| **Fase 1 — Circuito** | Circuito electrónico formado con el ESP32, LCD 16x2 I2C funcionando al 100% con las técnicas de diseño electrónico trabajado en Sistemas de Control. |
| **Fase 2 — API y BD** | Base de datos de mínimo 7 tablas relacionadas, API POO. |
| **Fase 3 — Streamlit** | Aplicación funcional con EDA trabajadas en el corte 1 con todas las recomendaciones. El aplicativo debe ser dinámico, permitiendo interactuar con cada unas de las variables. Adicionalmente vincular, matriz de correlación, limpieza básica. Dos algoritmo de Machine Learning. |
| **Fase 4 — Power BI** | Archivo .pbix conectado a PostgreSQL con 4 indicadores, 6 gráficos y 2 filtros aplicando estilo, colores acordes. |
| **Fase 5 — Sustentación** | Representante de cada equipo el cual estará disponible para la verificación de funcionamiento y/o preguntas. |

## 9. Rúbrica de evaluación detallada
La evaluación se distribuye en cinco fases, cada una con un peso porcentual sobre la nota final. Dentro de cada fase se evalúan criterios específicos con su respectiva ponderación interna.

### 9.1 Fase 1 — Circuito electrónico (30%)
| Criterio | Peso | Descripción de desempeño esperado |
| :--- | :--- | :--- |
| Funcionamiento del circuito | 30% | El ESP32, los dos sensores y la LCD funcionan correctamente y muestran datos coherentes en tiempo real. |

### 9.2 Fase 2 — API y base de datos PostgreSQL (20%)
| Criterio | Peso | Descripción de desempeño esperado |
| :--- | :--- | :--- |
| Base de datos y API | 20% | Base de datos, almacenamiento, API, funcionamiento óptimo. |

### 9.3 Fase 3 — Analítica en Streamlit (25%)
| Criterio | Peso | Descripción de desempeño esperado |
| :--- | :--- | :--- |
| Calidad del análisis exploratorio (EDA). Predicción mediante dos algoritmos de ML | 25% | Análisis de datos, predicción de variables. |

### 9.4 Fase 4 — Visualización en Power BI (25%)
| Criterio | Peso | Descripción de desempeño esperado |
| :--- | :--- | :--- |
| Diseño del dashboard | 25% | Composición clara, jerarquía visual adecuada, uso correcto de KPIs, tarjetas y segmentadores. |

---
**Fecha:** 07/08/2026 06:15 pm En el orden indicado por el profesor
