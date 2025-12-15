# ai_analyzer.py (VERSIÓN FINAL LIMPIA)

from google import genai
from google.genai import types
import os
from datetime import datetime, timedelta
import re 
# IMPORTANTE: Importar SOLO las funciones necesarias del gestor de DB
from db_manager import execute_dynamic_query, main_db_setup 


# --- 1. CONFIGURACIÓN E INICIALIZACIÓN DEL CLIENTE GEMINI ---

# La clave será inyectada automáticamente por Render (variable de entorno).
# Usamos un valor de 'placeholder' si no se encuentra para evitar exponer la clave.
# Asegúrate de que la variable GEMINI_API_KEY esté en Render.
API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_FALLBACK_API_KEY_HERE") 

client = None # Inicializar cliente a None
try:
    if API_KEY != "YOUR_FALLBACK_API_KEY_HERE":
        client = genai.Client(api_key=API_KEY)
        print("INFO: Cliente Gemini inicializado correctamente.")
    else:
        print("ADVERTENCIA: Usando clave de API de fallback. Verifica la variable GEMINI_API_KEY en Render.")
except Exception as e:
    print(f"ERROR CRÍTICO: No se pudo inicializar el cliente Gemini. Detalle: {e}")
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
# (Las funciones de utilidad y contexto permanecen iguales)

def get_fechas_analisis():
    """Devuelve las fechas clave para el contexto temporal de la IA."""
    now = datetime.now()
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
    prompt = f"""
    Esa un conversor de lenguaje natural a SQL para una base de datos SQLite.
    Tu objetivo es generar la consulta SQL SELECT más precisa y eficiente.

    --- REGLAS CRÍTICAS ---
    1. **NO** devuelvas explicaciones, comentarios, o texto adicional.
    2. **SOLO** devuelve la sentencia SQL de tipo SELECT.
    3. Usa JOINs para conectar las 7 tablas del esquema.
    4. Para consultas temporales como 'el mes pasado', usa el contexto de fecha y la función DATE/STRFTIME de SQLite.

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
                temperature=0.0,
                system_instruction="SOLO responde con la sentencia SQL SELECT, sin texto adicional."
            )
        )
        
        raw_text = response.text.strip()
        
        # ** LÓGICA DE LIMPIEZA ROBÚSTA (REGEX) **
        sql_match = re.search(r'SELECT.*', raw_text, re.IGNORECASE | re.DOTALL)
        
        if sql_match:
            sql_query = sql_match.group(0).strip()
            
            if ';' in sql_query:
                sql_query = sql_query.split(';')[0].strip()
            
            return sql_query, None
        else:
            return raw_text, "El modelo no generó una sentencia SQL que comience con 'SELECT'."

    except genai.errors.APIError as e:
        return None, f"Error al generar SQL con Gemini: {e}"
    except Exception as e:
        return None, f"Error desconocido al generar SQL: {e}"


# --- 5. INTERPRETACIÓN DE RESULTADOS ---
# (La función de interpretación permanece igual)

def generate_ai_response(question, columns, data, sql_query, db_error):
    """
    Interpreta los resultados de la DB y genera una respuesta conversacional.
    """
    if not client:
        return "ERROR: Cliente Gemini no inicializado. No se puede interpretar la respuesta."
    
    if db_error:
        data_summary = f"ERROR DE BASE DE DATOS: {db_error}"
    else:
        # --- BLINDAJE DE FORMATO: Aseguramos la estructura para el modelo ---
        data_summary = f"Columnas: {columns}\n\nRESULTADOS DE DATOS OBTENIDOS:\n"
        
        is_empty = not data or (len(data) == 1 and all(d is None for d in data[0]))
        
        if is_empty:
            data_summary += "[No se encontraron registros de datos o los valores son NULL/None.]"
        
        else:
            limit = 50 
            
            for i, row in enumerate(data):
                if i < limit:
                    row_data = ', '.join([f"{col}: {val}" for col, val in zip(columns, row)])
                    data_summary += f"- Fila {i+1}: {row_data}\n"
                else:
                    data_summary += f"...y {len(data) - limit} filas más (truncado).\n"
                    break
        # ----------------------------------------------------------------------


    # Prompt para la Interpretación
    prompt = f"""
    Efectuaste la siguiente consulta SQL: {sql_query}
    Eres un Analista de Datos Conversacional. Analiza los siguientes resultados
    y provee una respuesta clara y concisa a la pregunta del usuario.

    --- REGLAS DE RESPUESTA ---
    1. Utiliza un tono profesional, claro y conciso.
    2. Si los resultados son datos tabulares, utiliza **formato Markdown (tablas)** para presentarlos.
    3. Si el resultado es un único valor (ej. una suma o promedio), solo proporciona el número y explica a qué corresponde.
    4. NO muestres el código SQL ni los datos crudos, solo la interpretación.
    5. Si el resultado de la DB contiene valores NULL/None, explica de forma concisa que la información solicitada no está disponible.

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