# ai_analyzer.py (VERSIÓN 1.5 FLASH - OPTIMIZADA)

from google import genai
from google.genai import types
import os
from datetime import datetime
import re 

# --- 1. CONFIGURACIÓN ---
API_KEY = os.environ.get("GEMINI_API_KEY") 
# Volvemos al 1.5 que tiene límites de cuota más amplios en el plan gratuito
MODEL_NAME = 'gemini-1.5-flash' 

client = None
if API_KEY:
    try:
        client = genai.Client(api_key=API_KEY)
        print(f"INFO: Cliente Gemini ({MODEL_NAME}) inicializado.")
    except Exception as e:
        print(f"ERROR: {e}")

# --- 2. ESQUEMA DE LA BASE DE DATOS (PostgreSQL para Render) ---
ESQUEMA_DB = """
Ciudades (id_ciudad INT PRIMARY KEY, nombre_ciudad TEXT, pais TEXT);
Categorias (id_categoria INT PRIMARY KEY, nombre_categoria TEXT);
Sucursales (id_sucursal INT PRIMARY KEY, nombre_sucursal TEXT, id_ciudad INT REFERENCES Ciudades(id_ciudad));
Clientes (id_cliente INT PRIMARY KEY, nombre TEXT, apellido TEXT, edad INT, id_ciudad INT REFERENCES Ciudades(id_ciudad), email TEXT);
Productos (id_producto SERIAL PRIMARY KEY, nombre TEXT, precio DECIMAL, stock INT, id_categoria INT REFERENCES Categorias(id_categoria));
Ventas (id_venta SERIAL PRIMARY KEY, id_cliente INT REFERENCES Clientes(id_cliente), id_sucursal INT REFERENCES Sucursales(id_sucursal), fecha_venta TIMESTAMP, total DECIMAL);
DetalleVenta (id_detalle SERIAL PRIMARY KEY, id_venta INT REFERENCES Ventas(id_venta), id_producto INT REFERENCES Productos(id_producto), cantidad INT, subtotal DECIMAL);
"""

# --- 3. UTILIDADES ---
def get_fechas_analisis():
    now = datetime.now()
    return {"fecha_actual": now.strftime("%Y-%m-%d %H:%M:%S")}

# --- 4. GENERACIÓN DE SQL ---
def generate_sql_query(question, correction_context=None):
    if not client: return None, "Error de Cliente"
    
    fechas = get_fechas_analisis()
    
    LOGICA_NEGOCIO = """
    1. 'Clientes de Alto Valor': Gasto total > promedio * 2.
    2. 'Clientes en Riesgo': Compras < promedio de compras.
    3. Usa ILIKE para nombres de ciudades o sucursales.
    """

    prompt = f"""
    Eres un Analista Senior. Traduce a SQL para POSTGRESQL.
    {LOGICA_NEGOCIO}
    --- ESQUEMA ---
    {ESQUEMA_DB}
    --- CONTEXTO ---
    Fecha: {fechas['fecha_actual']}
    Pregunta: {question}
    {f'CORREGIR: {correction_context}' if correction_context else ''}
    Genera SOLO el código SQL SELECT:
    """
    
    try:
        response = client.models.generate_content(
            model=MODEL_NAME, 
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                system_instruction="Generar solo SQL SELECT para PostgreSQL puro."
            )
        )
        
        sql_raw = response.text.strip()
        sql_query = re.search(r'SELECT.*', sql_raw, re.IGNORECASE | re.DOTALL)
        
        if sql_query:
            clean_sql = sql_query.group(0).replace('```sql', '').replace('```', '').split(';')[0].strip()
            return clean_sql, None
        return sql_raw, "Error de formato"

    except Exception as e:
        return None, str(e)

# --- 5. INTERPRETACIÓN ---
def generate_ai_response(question, columns, data, sql_query, db_error):
    if not client: return "Error de Cliente"
    
    data_summary = f"Columnas: {columns}\nDatos: {data[:20]}"
    
    prompt = f"""
    Eres un Analista de Negocios. Interpreta estos resultados.
    Pregunta: {question}
    Resultados: {data_summary}
    Responde con Tabla Markdown y análisis ejecutivo.
    """
    
    try:
        response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        return response.text
    except Exception as e:
        return f"Error en interpretación: {e}"