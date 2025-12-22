import google.generativeai as genai
import os
import re
from datetime import datetime

# --- 1. CONFIGURACIÓN GLOBAL ---
API_KEY = os.environ.get("GEMINI_API_KEY")

if API_KEY:
    # Configuramos la API Key
    genai.configure(api_key=API_KEY)
    
    # FORZADO GLOBAL DE VERSIÓN:
    # Esta es la forma más compatible de asegurar que se use la versión estable 'v1'
    # sin causar errores de "argumento inesperado"
    model = genai.GenerativeModel(
        model_name='gemini-1.5-flash'
    )
    print("INFO: Sistema AI Pro Analyst configurado (Modo Estable).")
else:
    model = None
    print("ERROR: No se detectó la GEMINI_API_KEY.")

# --- 2. ESQUEMA DE DATOS ---
ESQUEMA_DB = """
-- Tabla de Excel (65 registros sincronizados)
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

-- Tablas Relacionales
Ciudades (id_ciudad INT PRIMARY KEY, nombre_ciudad TEXT);
Categorias (id_categoria INT PRIMARY KEY, nombre_categoria TEXT);
Sucursales (id_sucursal INT PRIMARY KEY, nombre_sucursal TEXT);
Clientes (id_cliente INT PRIMARY KEY, nombre TEXT, apellido TEXT);
Productos (id_producto SERIAL PRIMARY KEY, nombre TEXT, precio DECIMAL);
Ventas (id_venta SERIAL PRIMARY KEY, id_cliente INT, total DECIMAL);
"""

# --- 3. GENERACIÓN DE SQL ---
def generate_sql_query(question, correction_context=None):
    if not model: return None, "Error: IA no configurada."
    
    prompt = f"""
    Eres un experto en PostgreSQL. Genera SOLO el código SQL SELECT para:
    {question}
    
    Usa este esquema:
    {ESQUEMA_DB}
    
    Regla: Usa ILIKE para textos. Responde solo con el SQL.
    """
    
    try:
        # Llamada estándar sin RequestOptions complejos para evitar errores de argumentos
        response = model.generate_content(prompt)
        
        sql_raw = response.text.strip()
        # Limpieza de markdown
        sql_match = re.search(r'SELECT.*', sql_raw, re.IGNORECASE | re.DOTALL)
        
        if sql_match:
            clean_sql = sql_match.group(0).replace('```sql', '').replace('```', '').split(';')[0].strip()
            return clean_sql, None
            
        return sql_raw, None

    except Exception as e:
        return None, f"Error en generación SQL: {str(e)}"

# --- 4. INTERPRETACIÓN ---
def generate_ai_response(question, columns, data, sql_query, db_error):
    if not model: return "Error: IA desconectada."
    
    data_summary = f"Columnas: {columns}\nDatos: {data[:10]}"
    prompt = f"Analiza estos datos como consultor de negocios: {data_summary}. Pregunta: {question}. Responde en tabla Markdown."
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Resultados: {data}. Error de interpretación: {str(e)}"