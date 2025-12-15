# ai_analyzer.py (Versión Final, Optimizada para Render)

from google import genai
from google.genai import types
import os
from datetime import datetime, timedelta
import re # <-- Importado para la limpieza robusta de SQL

# --- 1. CONFIGURACIÓN E INICIALIZACIÓN DEL CLIENTE GEMINI ---

# La clave será inyectada automáticamente por Render (variable de entorno).
# Si no la encuentra (ej. pruebas locales sin env), usamos la temporal que proporcionaste.
API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyCqOU1flrQJgVtGp_s9VeNOum_o5C8b6vA") # Usa la clave que subiste

try:
    # Inicializa el cliente usando la clave obtenida
    client = genai.Client(api_key=API_KEY)
    print("INFO: Cliente Gemini inicializado correctamente.")
except Exception as e:
    print(f"ERROR CRÍTICO: No se pudo inicializar el cliente Gemini. La API Key podría ser inválida o faltar. Detalle: {e}")
    client = None


# --- 2. ESQUEMA COMPLETO DE LA BASE DE DATOS ---
ESQUEMA_DB = """
-- Esquema de la Base de Datos SQLite (supermercado.db):
-- La base de datos es relacional y contiene información de ventas, productos y clientes.

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

# --- 3. FUNCIONES DE UTILIDAD Y CONTEXTO DE FECHA ---
def get_fechas_analisis():
    """Devuelve las fechas clave para el contexto temporal de la IA."""
    now = datetime.now()
    # Para la referencia de "el mes pasado", calculamos el primer día del mes actual y luego retrocedemos
    primer_dia_mes_actual = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    ultimo_dia_mes_pasado = primer_dia_mes_actual - timedelta(days=1)
    
    return {
        "fecha_actual_iso": now.strftime("%Y-%m-%d %H:%M:%S"),
        "mes_actual_YYYY_MM": now.strftime("%Y-%m"),
        "ultimo_dia_mes_pasado_iso": ultimo_dia_mes_pasado.strftime("%Y-%m-%d")
    }


# --- 4. GENERACIÓN DE CONSULTA SQL ---
def generate_sql_query(question, correction_context=None):
    """
    Llama a Gemini para convertir la pregunta del usuario en una consulta SQL.
    """
    if not client:
        return None, "ERROR: Cliente Gemini no inicializado o API Key faltante."
    
    fechas = get_fechas_analisis()

    correction_instruction = ""
    if correction_context:
        correction_instruction = f"""
        *** CORRECCIÓN REQUERIDA ***
        Tu consulta SQL anterior falló al ejecutarse. Por favor, revisa el ESQUEMA y el error:
        '{correction_context}'.
        Genera una NUEVA y CORRECTA sentencia SQL SELECT para la pregunta original.
        """

    # --- PROMPT DE SISTEMA CRÍTICO ---
    # El prompt está diseñado para obligar a la IA a responder SOLO con el código.
    prompt = f"""
    Eres un conversor de lenguaje natural a SQL para una base de datos SQLite.
    Tu objetivo es generar la consulta SQL SELECT más precisa y eficiente.

    --- REGLAS CRÍTICAS ---
    1. **NO** devuelvas explicaciones, comentarios, o texto adicional.
    2. **SOLO** devuelve la sentencia SQL de tipo SELECT.
    3. Usa JOINs para conectar las 7 tablas del esquema.
    4. Para consultas temporales como 'el mes pasado', usa el contexto de fecha y la función STRFTIME de SQLite.

    --- CONTEXTO DE TIEMPO ---
    * Fecha y hora actual (NOW): {fechas["fecha_actual_iso"]}
    * Último día del mes pasado: {fechas["ultimo_dia_mes_pasado_iso"]}
    
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
            config=types.GenerateContentConfig(
                temperature=0.0, # Mantenemos baja para precisión
                system_instruction="SOLO responde con la sentencia SQL SELECT, sin texto adicional."
            )
        )
        
        raw_text = response.text.strip()
        
        # ** LÓGICA DE LIMPIEZA ROBÚSTA (REGEX) **
        # Buscamos la primera aparición de SELECT (sin importar mayúsculas/minúsculas)
        # y extraemos el contenido hasta el final o hasta el primer punto y coma.
        sql_match = re.search(r'SELECT.*', raw_text, re.IGNORECASE | re.DOTALL)
        
        if sql_match:
            sql_query = sql_match.group(0).strip()
            
            # Limpieza: eliminar cualquier cosa después del primer punto y coma, si existe
            if ';' in sql_query:
                sql_query = sql_query.split(';')[0].strip()
            
            return sql_query, None
        else:
            # Si no encuentra 'SELECT', devolvemos la salida cruda para depuración
            return raw_text, "El modelo no generó una sentencia SQL que comience con 'SELECT'."

    except genai.errors.APIError as e:
        # Esto capturaría errores como 429 Resource Exhausted o clave inválida
        return None, f"Error al generar SQL con Gemini: {e}"
    except Exception as e:
        return None, f"Error desconocido al generar SQL: {e}"


# --- 5. INTERPRETACIÓN DE RESULTADOS ---
def generate_ai_response(question, columns, data, sql_query, db_error):
    """
    Interpreta los resultados de la DB y genera una respuesta conversacional.
    """
    if not client:
        return "ERROR: Cliente Gemini no inicializado. No se puede interpretar la respuesta."
    
    # Manejo de errores de DB (si pasamos esta etapa es que la autocorrección falló)
    if db_error:
        data_summary = f"ERROR DE BASE DE DATOS: {db_error}"
    else:
        # Formatear columnas y datos para el prompt
        data_summary = f"Columnas: {columns}\nDatos:\n"
        
        # Limitar la salida para evitar exceder el token limit en caso de grandes resultados
        limit = 50 
        for i, row in enumerate(data):
            if i < limit:
                data_summary += f"{row}\n"
            else:
                data_summary += f"...y {len(data) - limit} filas más (truncado).\n"
                break
    
    # Prompt para la Interpretación: Pide formato Markdown si es necesario.
    prompt = f"""
    Efectuaste la siguiente consulta SQL: {sql_query}
    Eres un Analista de Datos Conversacional. Analiza los siguientes resultados
    y provee una respuesta clara y concisa a la pregunta del usuario.

    --- REGLAS DE RESPUESTA ---
    1. Utiliza un tono profesional, claro y conciso.
    2. Si los resultados son datos tabulares, utiliza **formato Markdown (tablas)** para presentarlos.
    3. Si el resultado es un único valor (ej. una suma), solo proporciona el número y explica a qué corresponde.
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
    except Exception as e:
        return f"Error inesperado al interpretar la respuesta de IA: {e}"