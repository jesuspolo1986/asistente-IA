from google import genai
from google.genai import types
import os
from datetime import datetime
import re 

# --- 1. CONFIGURACIÓN ---
# Usamos 1.5-flash para máxima estabilidad en Render
API_KEY = os.environ.get("GEMINI_API_KEY") 
MODEL_NAME = 'gemini-1.5-flash'

client = None
if API_KEY:
    try:
        client = genai.Client(api_key=API_KEY)
        print(f"INFO: Cliente Gemini ({MODEL_NAME}) inicializado.")
    except Exception as e:
        print(f"ERROR: {e}")

# --- 2. ESQUEMA DE LA BASE DE DATOS (Actualizado para Postgres) ---
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
    return {
        "fecha_actual": now.strftime("%Y-%m-%d %H:%M:%S"),
        "mes_actual": now.strftime("%Y-%m"),
    }

# --- 4. GENERACIÓN DE SQL ---
def generate_sql_query(question, correction_context=None):
    if not client: return None, "Error de Cliente Gemini"
    
    fechas = get_fechas_analisis()
    
    # Ajustamos el prompt para especificar POSTGRESQL
    prompt = f"""
    Eres un Analista de Datos Senior experto en POSTGRESQL.
    Traduce la pregunta a una consulta SQL válida para PostgreSQL.

    --- REGLAS DE NEGOCIO ---
    1. 'Clientes de Alto Valor': Aquellos con gasto total > promedio * 2.
    2. Usa siempre JOINs explícitos.
    3. Para comparaciones de texto con nombres, usa siempre ILIKE en lugar de LIKE para que no importe mayúsculas/minúsculas.
    4. Si se pide 'hoy' o fechas recientes, usa la fecha actual proporcionada.

    --- ESQUEMA ---
    {ESQUEMA_DB}

    --- CONTEXTO ---
    Fecha actual: {fechas['fecha_actual']}
    
    Pregunta: {question}
    {f'ERROR A CORREGIR: {correction_context}' if correction_context else ''}
    
    Genera únicamente el código SQL SELECT sin explicaciones ni bloques de código markdown:
    """
    
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                system_instruction="Generar solo SQL puro para PostgreSQL. No usar markdown."
            )
        )
        
        # Limpieza del SQL generado
        sql_text = response.text.strip()
        sql_query = re.search(r'SELECT.*', sql_text, re.IGNORECASE | re.DOTALL)
        
        if sql_query:
            clean_sql = sql_query.group(0).replace('```sql', '').replace('```', '').split(';')[0].strip()
            return clean_sql, None
        return sql_text, "Error de formato SQL"

    except Exception as e:
        return None, str(e)

# --- 5. INTERPRETACIÓN ---
def generate_ai_response(question, columns, data, sql_query, db_error):
    if not client: return "Error de Cliente Gemini"
    
    data_summary = f"Columnas: {columns}\nDatos: {data[:25]}" 
    if not data: data_summary = "La consulta no devolvió resultados."

    prompt = f"""
    Eres un Consultor Estratégico de Negocios. Interpreta los resultados de la base de datos de un supermercado.
    
    Pregunta del usuario: {question}
    Resultados obtenidos: {data_summary}
    SQL ejecutado: {sql_query}
    
    Instrucciones de formato:
    1. Si hay datos, presenta una tabla Markdown profesional.
    2. Incluye un análisis de 2 o 3 puntos clave (insights).
    3. Usa un tono ejecutivo y amable.
    4. No menciones IDs técnicos, usa los nombres de ciudades o productos.
    """
    
    try:
        response = client.models.generate_content(
            model=MODEL_NAME, 
            contents=prompt
        )
        return response.text
    except Exception as e:
        return f"Error en interpretación: {e}"