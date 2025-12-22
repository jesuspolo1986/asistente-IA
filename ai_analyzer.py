# ai_analyzer.py - VERSIÓN INTEGRADA CON CARGA DE EXCEL
from google import genai
from google.genai import types
import os
from datetime import datetime
import re 

# --- 1. CONFIGURACIÓN ---
API_KEY = os.environ.get("GEMINI_API_KEY") 
MODEL_NAME = 'gemini-1.5-flash' # Modelo balanceado para evitar error 429

client = None
if API_KEY:
    try:
        client = genai.Client(api_key=API_KEY)
        print(f"INFO: Cliente Gemini ({MODEL_NAME}) listo.")
    except Exception as e:
        print(f"ERROR: {e}")

# --- 2. ESQUEMA DE LA BASE DE DATOS (Incluye Tabla de Excel) ---
# Hemos añadido 'ventas_externas' que es donde pandas guarda los archivos subidos.
ESQUEMA_DB = """
-- Tablas Base:
Ciudades (id_ciudad INT PRIMARY KEY, nombre_ciudad TEXT, pais TEXT);
Categorias (id_categoria INT PRIMARY KEY, nombre_categoria TEXT);
Sucursales (id_sucursal INT PRIMARY KEY, nombre_sucursal TEXT, id_ciudad INT);
Clientes (id_cliente INT PRIMARY KEY, nombre TEXT, apellido TEXT, id_ciudad INT);
Productos (id_producto SERIAL PRIMARY KEY, nombre TEXT, precio DECIMAL, id_categoria INT);
Ventas (id_venta SERIAL PRIMARY KEY, id_cliente INT, id_sucursal INT, fecha_venta TIMESTAMP, total DECIMAL);

-- Tabla de Cargas de Excel/CSV:
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
    if not client: return None, "Error de Cliente"
    
    fechas = get_fechas_analisis()
    
    # Lógica para que la IA decida si usar las tablas base o la de Excel
    LOGICA_NEGOCIO = """
    1. Si el usuario pregunta por datos generales, prioriza la tabla 'ventas_externas' si las otras están vacías.
    2. Usa ILIKE para comparaciones de texto.
    3. 'Clientes de Alto Valor': Aquellos con total sumado > promedio * 2 en cualquiera de las tablas de ventas.
    """

    prompt = f"""
    Eres un Analista Senior de PostgreSQL. Traduce a SQL:
    {LOGICA_NEGOCIO}
    --- ESQUEMA ---
    {ESQUEMA_DB}
    --- CONTEXTO ---
    Fecha actual: {fechas['fecha_actual']}
    Pregunta: {question}
    {f'CORRECCIÓN: {correction_context}' if correction_context else ''}
    
    Genera SOLO el código SQL SELECT:
    """
    
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                system_instruction="Generar solo código SQL para PostgreSQL. Nada de explicaciones."
            )
        )
        
        sql_raw = response.text.strip()
        # Limpiar posibles bloques de código markdown
        sql_query = re.search(r'SELECT.*', sql_raw, re.IGNORECASE | re.DOTALL)
        
        if sql_query:
            clean_sql = sql_query.group(0).replace('```sql', '').replace('```', '').split(';')[0].strip()
            return clean_sql, None
        return sql_raw, "Formato SQL no detectado"

    except Exception as e:
        return None, str(e)

# --- 5. INTERPRETACIÓN DE RESULTADOS ---
def generate_ai_response(question, columns, data, sql_query, db_error):
    if not client: return "IA fuera de servicio."
    
    data_summary = f"Columnas: {columns}\nDatos obtenidos: {data[:25]}"
    if not data: data_summary = "La consulta no devolvió resultados."

    prompt_analisis = f"""
    Eres un Consultor de Negocios. Analiza estos resultados de la DB:
    Pregunta: {question}
    Datos: {data_summary}
    Instrucciones: Responde con una tabla Markdown profesional y un análisis breve de los hallazgos.
    """
    
    try:
        response = client.models.generate_content(model=MODEL_NAME, contents=prompt_analisis)
        return response.text
    except Exception as e:
        return f"Error al interpretar datos: {e}"