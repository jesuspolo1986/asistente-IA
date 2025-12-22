import google.generativeai as genai
import os
from datetime import datetime
import re 

# --- 1. CONFIGURACIÓN ESTABLE ---
API_KEY = os.environ.get("GEMINI_API_KEY")

if API_KEY:
    genai.configure(api_key=API_KEY)
    # Usamos la inicialización clásica que no falla con el 404 de v1beta
    model = genai.GenerativeModel('gemini-1.5-flash')
    print("INFO: Cliente Gemini 1.5-Flash inicializado correctamente.")
else:
    model = None
    print("ERROR: No se encontró la GEMINI_API_KEY")

# --- 2. ESQUEMA DE LA BASE DE DATOS ---
ESQUEMA_DB = """
Ciudades (id_ciudad INT PRIMARY KEY, nombre_ciudad TEXT);
Categorias (id_categoria INT PRIMARY KEY, nombre_categoria TEXT);
Sucursales (id_sucursal INT PRIMARY KEY, nombre_sucursal TEXT);
Clientes (id_cliente INT PRIMARY KEY, nombre TEXT, apellido TEXT);
Productos (id_producto SERIAL PRIMARY KEY, nombre TEXT, precio DECIMAL);
Ventas (id_venta SERIAL PRIMARY KEY, id_cliente INT, fecha_venta TIMESTAMP, total DECIMAL);

-- Tabla para archivos subidos
ventas_externas (
    fecha_venta TIMESTAMP, cliente TEXT, producto TEXT, 
    categoria TEXT, cantidad INT, precio_unitario DECIMAL, 
    total DECIMAL, sucursal TEXT
);
"""

# --- 3. GENERACIÓN DE SQL ---
def generate_sql_query(question, correction_context=None):
    if not model: return None, "IA no configurada"
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    prompt = f"""
    Eres un Analista Senior de PostgreSQL. 
    Traduce la pregunta a una consulta SQL SELECT válida usando este esquema:
    {ESQUEMA_DB}
    
    Contexto: Fecha de hoy {now}. 
    Si la pregunta refiere a datos externos o nuevos, usa 'ventas_externas'.
    Usa ILIKE para búsquedas de texto.
    
    Pregunta: {question}
    {f'Corrección previa: {correction_context}' if correction_context else ''}
    
    Responde SOLO con el código SQL:
    """
    
    try:
        # Método de generación estable
        response = model.generate_content(prompt)
        sql_raw = response.text.strip()
        
        # Limpieza de etiquetas markdown
        sql_clean = re.sub(r'```sql|```', '', sql_raw).strip()
        sql_match = re.search(r'SELECT.*', sql_clean, re.IGNORECASE | re.DOTALL)
        
        if sql_match:
            return sql_match.group(0).split(';')[0].strip(), None
        return sql_clean, "No se detectó un SELECT válido"
        
    except Exception as e:
        return None, f"Error en IA: {str(e)}"

# --- 4. INTERPRETACIÓN ---
def generate_ai_response(question, columns, data, sql_query, db_error):
    if not model: return "Error: IA no disponible."
    
    resumen = f"Columnas: {columns}\nDatos: {data[:10]}"
    
    prompt = f"""
    Eres un Consultor de Negocios. Interpreta estos resultados:
    Pregunta: {question}
    Resultados: {resumen}
    Crea una tabla Markdown y da una conclusión breve.
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Datos obtenidos: {data}. Error al interpretar: {e}"