# ai_analyzer.py (INICIALIZACIÓN CORREGIDA)

from google import genai
import os
from datetime import datetime, timedelta

# --- CLAVE TEMPORAL PARA PRUEBAS ---
# RECUERDA: EN PRODUCCIÓN (RENDER) ESTO SERÁ UNA VARIABLE DE ENTORNO.
# Si la clave no está en el entorno (os.environ), usamos la clave que proporcionaste.
API_KEY_TEMP = os.environ.get("GEMINI_API_KEY", "AIzaSyB_9StEcizaz8nYu0kuT5K35SY-flrzgFA")
try:
    # Intentamos inicializar usando la clave obtenida (ya sea de env o temporal)
    client = genai.Client(api_key=API_KEY_TEMP)
    # Verificamos que la clave sea válida si es la temporal
    if not API_KEY_TEMP or API_KEY_TEMP == "AIzaSyD83uHYIjVufKQL-9ZsP94sqg4Tkx2QYSM":
        print("INFO: Usando clave de respaldo para esta prueba.")
except Exception as e:
    print(f"ERROR CRÍTICO: No se pudo inicializar el cliente Gemini con la clave provista. {e}")
    client = None
# --- Esquema de la Base de Datos para Gemini (IMPORTANTE) ---
ESQUEMA_DB = """
-- Esquema de la Base de Datos SQLite (supermercado.db):

CREATE TABLE Ciudades (
    id_ciudad INTEGER PRIMARY KEY,
    nombre_ciudad TEXT,
    pais TEXT
);

CREATE TABLE Categorias (
    id_categoria INTEGER PRIMARY KEY,
    nombre_categoria TEXT
);

CREATE TABLE Sucursales (
    id_sucursal INTEGER PRIMARY KEY,
    nombre_sucursal TEXT,
    id_ciudad INTEGER,
    direccion TEXT,
    FOREIGN KEY (id_ciudad) REFERENCES Ciudades (id_ciudad)
);

CREATE TABLE Clientes (
    id_cliente INTEGER PRIMARY KEY,
    nombre TEXT,
    apellido TEXT,
    edad INTEGER,
    id_ciudad INTEGER,
    email TEXT,
    FOREIGN KEY (id_ciudad) REFERENCES Ciudades (id_ciudad)
);

CREATE TABLE Productos (
    id_producto INTEGER PRIMARY KEY,
    nombre TEXT,
    precio REAL,
    stock INTEGER,
    fecha_vencimiento TEXT, -- Formato YYYY-MM-DD
    id_categoria INTEGER,
    FOREIGN KEY (id_categoria) REFERENCES Categorias (id_categoria)
);

CREATE TABLE Ventas (
    id_venta INTEGER PRIMARY KEY,
    id_cliente INTEGER,
    id_sucursal INTEGER,
    fecha_venta TEXT, -- Formato YYYY-MM-DD HH:MM:SS
    total REAL,
    FOREIGN KEY (id_cliente) REFERENCES Clientes (id_cliente),
    FOREIGN KEY (id_sucursal) REFERENCES Sucursales (id_sucursal)
);

CREATE TABLE DetalleVenta (
    id_detalle INTEGER PRIMARY KEY,
    id_venta INTEGER,
    id_producto INTEGER,
    cantidad INTEGER,
    subtotal REAL,
    FOREIGN KEY (id_venta) REFERENCES Ventas (id_venta),
    FOREIGN KEY (id_producto) REFERENCES Productos (id_producto)
);
"""

# --- Funciones de Utilidad de Fecha ---
def get_fechas_analisis():
    """Devuelve la fecha actual y la fecha de hace 7 días para el contexto."""
    now = datetime.now()
    seven_days_ago = now - timedelta(days=7)
    
    return {
        "fecha_actual_iso": now.strftime("%Y-%m-%d %H:%M:%S"),
        "hace_7_dias_iso": seven_days_ago.strftime("%Y-%m-%d %H:%M:%S"),
        "mes_actual_YYYY_MM": now.strftime("%Y-%m")
    }

# --- Generación de SQL ---
def generate_sql_query(question, correction_context=None):
    """
    Llama a Gemini para convertir la pregunta del usuario en una consulta SQL.
    Acepta un contexto de corrección si el intento anterior falló.
    """
    if not client:
        return None, "ERROR: Cliente Gemini no inicializado o API Key faltante."
    
    # Contexto de fechas para que Gemini genere filtros de tiempo correctos
    fechas = get_fechas_analisis()

    correction_instruction = ""
    if correction_context:
        correction_instruction = f"""
        *** CORRECCIÓN REQUERIDA ***
        Tu consulta SQL anterior falló al ejecutarse. Por favor, revisa cuidadosamente el esquema
        y el error reportado. Genera una NUEVA y CORRECTA sentencia SQL SELECT para la pregunta original.
        Detalle del Error Anterior: {correction_context}
        """

    # Prompt de sistema especializado en la generación de SQL
    prompt = f"""
    Eres un conversor de lenguaje natural a SQL para una base de datos SQLite.
    Tu objetivo es generar la consulta SQL más precisa y eficiente.

    --- REGLAS CRÍTICAS ---
    1. **NO** devuelvas explicaciones, comentarios, o texto adicional.
    2. **SOLO** devuelve la sentencia SQL de tipo SELECT.
    3. Asegúrate de que la consulta sea válida para el ESQUEMA proporcionado.
    4. Usa JOINs para conectar tablas (ej. Productos con DetalleVenta).

    --- FECHAS Y CONTEXTO DE TIEMPO ---
    * Fecha y hora actual (NOW): {fechas["fecha_actual_iso"]}
    * Fecha de hace 7 días: {fechas["hace_7_dias_iso"]}
    * Mes y Año Actual (YYYY-MM): {fechas["mes_actual_YYYY_MM"]}
    * Usa la función STRFTIME de SQLite para filtrar por fechas relativas.

    --- INSTRUCCIÓN ADICIONAL ---
    {correction_instruction}
    
    --- ESQUEMA DE LA BASE DE DATOS ---
    {ESQUEMA_DB}

    --- PREGUNTA DEL USUARIO ---
    {question}
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                temperature=0.0 # Baja temperatura para precisión en SQL
            )
        )
        sql_query = response.text.strip()
        # Limpieza simple para asegurar que no haya texto antes o después del SQL
        if sql_query.lower().startswith('select'):
            return sql_query, None
        else:
            return sql_query, "El modelo no generó una sentencia SQL válida."

    except genai.errors.APIError as e:
        return None, f"Error al generar SQL con Gemini: {e}"
    except Exception as e:
        return None, f"Error desconocido al generar SQL: {e}"

# --- Interpretación de Resultados ---
def generate_ai_response(question, columns, data, sql_query, db_error):
    """
    Interpreta los resultados de la DB o el error y genera una respuesta conversacional.
    """
    if not client:
        return "ERROR: Cliente Gemini no inicializado. No se puede interpretar la respuesta."
    
    if db_error:
        # Esto solo debería llamarse si la autocorrección falló en ambos intentos
        data_summary = f"ERROR DE BASE DE DATOS: {db_error}"
    else:
        # Formatear columnas y datos para el prompt
        data_summary = f"Columnas: {columns}\nDatos:\n"
        
        # Limitar la salida para no exceder el token limit en caso de grandes resultados
        limit = 100
        for i, row in enumerate(data):
            if i < limit:
                data_summary += f"{row}\n"
            else:
                data_summary += f"...y {len(data) - limit} filas más (truncado).\n"
                break
    
    # --- Prompt para la Interpretación ---
    prompt = f"""
    Eres un Analista de Datos Conversacional. Tu tarea es analizar los resultados
    de la base de datos y proveer una respuesta clara y concisa a la pregunta del usuario.

    --- REGLAS DE RESPUESTA ---
    1. Utiliza un tono profesional pero amigable.
    2. Si los resultados son datos tabulares (múltiples filas y columnas), utiliza **formato Markdown (tablas)** para presentarlos.
    3. Si el resultado es un único número (ej. una suma o promedio), proporciona el número y explica a qué corresponde.
    4. NO muestres el código SQL ni los datos crudos, solo la interpretación.

    --- CONTEXTO DE LA CONSULTA ---
    Pregunta Original: "{question}"
    
    --- RESULTADOS DE LA BASE DE DATOS ---
    {data_summary}
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        return response.text
    except genai.errors.APIError as e:
        return f"Error inesperado al interpretar la respuesta de IA: {e}"
    except Exception as e:
        return f"Error desconocido al interpretar la respuesta: {e}"