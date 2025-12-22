from google import genai
from google.genai import types
import os
from datetime import datetime
import re 

# --- 1. CONFIGURACIÓN ---
API_KEY = os.environ.get("GEMINI_API_KEY") 

# IMPORTANTE: En la nueva SDK 'google-genai', usamos solo el nombre.
# Si sigue dando 404, la SDK está intentando usar v1beta internamente.
MODEL_NAME = 'gemini-1.5-flash' 

client = None
if API_KEY:
    try:
        # Inicializamos sin parámetros extra para que use la API v1 (Estable) por defecto
        client = genai.Client(api_key=API_KEY)
        print(f"INFO: Cliente Gemini ({MODEL_NAME}) listo.")
    except Exception as e:
        print(f"ERROR: {e}")

# --- 2. ESQUEMA ---
ESQUEMA_DB = """
Ciudades (id_ciudad INT PRIMARY KEY, nombre_ciudad TEXT, pais TEXT);
Categorias (id_categoria INT PRIMARY KEY, nombre_categoria TEXT);
Sucursales (id_sucursal INT PRIMARY KEY, nombre_sucursal TEXT, id_ciudad INT REFERENCES Ciudades(id_ciudad));
Clientes (id_cliente INT PRIMARY KEY, nombre TEXT, apellido TEXT, edad INT, id_ciudad INT REFERENCES Ciudades(id_ciudad), email TEXT);
Productos (id_producto SERIAL PRIMARY KEY, nombre TEXT, precio DECIMAL, stock INT, id_categoria INT REFERENCES Categorias(id_categoria));
Ventas (id_venta SERIAL PRIMARY KEY, id_cliente INT REFERENCES Clientes(id_cliente), id_sucursal INT REFERENCES Sucursales(id_sucursal), fecha_venta TIMESTAMP, total DECIMAL);
DetalleVenta (id_detalle SERIAL PRIMARY KEY, id_venta INT REFERENCES Ventas(id_venta), id_producto INT REFERENCES Productos(id_producto), cantidad INT, subtotal DECIMAL);
"""

def get_fechas_analisis():
    now = datetime.now()
    return {"fecha_actual": now.strftime("%Y-%m-%d %H:%M:%S")}

# --- 4. GENERACIÓN DE SQL ---
def generate_sql_query(question, correction_context=None):
    if not client: return None, "Error: Cliente no inicializado"
    
    fechas = get_fechas_analisis()
    prompt = f"""
    Eres un Analista Senior de PostgreSQL. 
    Traduce a SQL: {question}
    Esquema: {ESQUEMA_DB}
    Fecha: {fechas['fecha_actual']}
    {f'Error previo: {correction_context}' if correction_context else ''}
    Genera solo el código SQL SELECT.
    """
    
    try:
        # CAMBIO CRÍTICO: Usamos el modelo tal cual, la SDK v1.0+ 
        # debería mapearlo a la versión estable de la API.
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                system_instruction="Generar solo SQL puro para PostgreSQL."
            )
        )
        
        sql_text = response.text.strip()
        sql_text = re.sub(r'```(?:sql)?|```', '', sql_text).strip()
        sql_match = re.search(r'SELECT.*', sql_text, re.IGNORECASE | re.DOTALL)
        
        if sql_match:
            return sql_match.group(0).split(';')[0].strip(), None
        return sql_text, "Formato SQL inválido"

    except Exception as e:
        # Capturamos el error exacto para diagnosticar
        return None, f"Error en generate_sql_query: {str(e)}"

# --- 5. INTERPRETACIÓN ---
def generate_ai_response(question, columns, data, sql_query, db_error):
    if not client: return "Error: IA Offline."
    
    data_summary = f"Columnas: {columns}\nDatos: {data[:20]}"
    prompt_analisis = f"Analiza estos datos de supermercado para responder: {question}\nDatos: {data_summary}"
    
    try:
        # Usamos la misma llamada simplificada
        response = client.models.generate_content(model=MODEL_NAME, contents=prompt_analisis)
        return response.text
    except Exception as e:
        return f"Error en interpretación: {e}"