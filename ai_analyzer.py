# ai_analyzer.py - VERSIÓN BLINDADA (SOLUCIÓN ERROR 404)
from google import genai
from google.genai import types
import os
from datetime import datetime
import re 

# --- 1. CONFIGURACIÓN ---
API_KEY = os.environ.get("GEMINI_API_KEY") 
# Usamos el nombre simplificado que la nueva SDK prefiere
MODEL_NAME = 'gemini-1.5-flash' 

client = None
if API_KEY:
    try:
        # IMPORTANTE: No forzamos versión de API para que la SDK maneje la compatibilidad
        client = genai.Client(api_key=API_KEY)
        print(f"INFO: Cliente Gemini ({MODEL_NAME}) inicializado con éxito.")
    except Exception as e:
        print(f"ERROR CRÍTICO: No se pudo conectar con Gemini: {e}")

# --- 2. ESQUEMA DE LA BASE DE DATOS ---
ESQUEMA_DB = """
-- Tablas Base:
Ciudades (id_ciudad INT PRIMARY KEY, nombre_ciudad TEXT, pais TEXT);
Categorias (id_categoria INT PRIMARY KEY, nombre_categoria TEXT);
Sucursales (id_sucursal INT PRIMARY KEY, nombre_sucursal TEXT, id_ciudad INT);
Clientes (id_cliente INT PRIMARY KEY, nombre TEXT, apellido TEXT, id_ciudad INT);
Productos (id_producto SERIAL PRIMARY KEY, nombre TEXT, precio DECIMAL, id_categoria INT);
Ventas (id_venta SERIAL PRIMARY KEY, id_cliente INT, id_sucursal INT, fecha_venta TIMESTAMP, total DECIMAL);

-- Tabla de Cargas de Excel/CSV (Donde se suben tus archivos):
ventas_externas (
    fecha_venta TIMESTAMP, 
    cliente TEXT, 
    producto TEXT, 
    categoria TEXT, 
    cantidad INT, 
    precio_unitario DECIMAL, 
    total DECIMAL, 
    sucursal TEXT
);
"""

# --- 3. UTILIDADES ---
def get_fechas_analisis():
    now = datetime.now()
    return {"fecha_actual": now.strftime("%Y-%m-%d %H:%M:%S")}

# --- 4. GENERACIÓN DE SQL ---
def generate_sql_query(question, correction_context=None):
    if not client: return None, "Error: Cliente AI no inicializado"
    
    fechas = get_fechas_analisis()
    
    LOGICA_NEGOCIO = """
    1. Si la pregunta es sobre el archivo subido o datos recientes, consulta 'ventas_externas'.
    2. Usa siempre ILIKE para textos (ej. nombre ILIKE '%valor%').
    3. Asegúrate de que el SQL sea compatible con PostgreSQL.
    """

    prompt = f"""
    Eres un Analista Senior de PostgreSQL. 
    Traduce la pregunta a una consulta SQL válida.
    {LOGICA_NEGOCIO}
    --- ESQUEMA ---
    {ESQUEMA_DB}
    --- CONTEXTO ---
    Fecha: {fechas['fecha_actual']}
    Pregunta: {question}
    {f'CORRECCIÓN REQUERIDA: {correction_context}' if correction_context else ''}
    
    Responde ÚNICAMENTE con el código SQL SELECT:
    """
    
    try:
        # Llamada optimizada para evitar el error 404 de versión de modelo
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                system_instruction="Eres un bot que solo devuelve código SQL SELECT para PostgreSQL. Sin explicaciones."
            )
        )
        
        sql_raw = response.text.strip()
        # Extraer solo el SELECT en caso de que la IA incluya texto extra
        sql_query = re.search(r'SELECT.*', sql_raw, re.IGNORECASE | re.DOTALL)
        
        if sql_query:
            clean_sql = sql_query.group(0).replace('```sql', '').replace('```', '').split(';')[0].strip()
            return clean_sql, None
        return sql_raw, "Formato SQL no detectado"

    except Exception as e:
        # Capturamos el error para depuración en los logs de Render
        print(f"DETALLE ERROR IA: {str(e)}")
        return None, f"Error en generación SQL: {str(e)}"

# --- 5. INTERPRETACIÓN ---
def generate_ai_response(question, columns, data, sql_query, db_error):
    if not client: return "Error: IA no disponible."
    
    data_summary = f"Columnas: {columns}\nDatos: {data[:15]}"
    if not data: data_summary = "No se encontraron datos para esta consulta."

    prompt_analisis = f"""
    Eres un Consultor de Negocios Senior.
    Pregunta del cliente: {question}
    Resultados obtenidos: {data_summary}
    Tarea: Presenta los datos en una tabla Markdown y da una conclusión estratégica breve.
    """
    
    try:
        response = client.models.generate_content(
            model=MODEL_NAME, 
            contents=prompt_analisis
        )
        return response.text
    except Exception as e:
        return f"Resultados obtenidos: {data}. (Nota: Hubo un error en la interpretación: {e})"