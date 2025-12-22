import google.generativeai as genai
from google.generativeai.types import RequestOptions
import os
import re
from datetime import datetime

# --- 1. CONFIGURACIÓN DE SEGURIDAD ---
# Usamos la librería estándar para evitar conflictos de rutas beta
API_KEY = os.environ.get("GEMINI_API_KEY")

if API_KEY:
    genai.configure(api_key=API_KEY)
    # Inicialización del modelo estable
    model = genai.GenerativeModel('gemini-1.5-flash')
    print("INFO: Sistema AI Pro Analyst inicializado en versión estable (v1).")
else:
    model = None
    print("ERROR: No se detectó la GEMINI_API_KEY en las variables de entorno.")

# --- 2. ESQUEMA DE DATOS (Incluye tus 65 registros de Excel) ---
ESQUEMA_DB = """
-- TABLA DE EXCEL (Cargas externas)
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

-- TABLAS DEL SISTEMA (Relacionales)
Ciudades (id_ciudad INT PRIMARY KEY, nombre_ciudad TEXT);
Categorias (id_categoria INT PRIMARY KEY, nombre_categoria TEXT);
Sucursales (id_sucursal INT PRIMARY KEY, nombre_sucursal TEXT, id_ciudad INT);
Clientes (id_cliente INT PRIMARY KEY, nombre TEXT, apellido TEXT);
Productos (id_producto SERIAL PRIMARY KEY, nombre TEXT, precio DECIMAL);
Ventas (id_venta SERIAL PRIMARY KEY, id_cliente INT, total DECIMAL);
"""

# --- 3. GENERACIÓN DE SQL (FORZADO V1) ---
def generate_sql_query(question, correction_context=None):
    if not model: return None, "Error: IA no configurada."
    
    fechas = {"actual": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    
    prompt = f"""
    Eres un Analista de Datos Senior especializado en PostgreSQL.
    Tu tarea es traducir la pregunta del usuario a una consulta SQL SELECT válida.
    
    ESQUEMA DISPONIBLE:
    {ESQUEMA_DB}
    
    REGLAS:
    1. Si la pregunta es sobre ventas recientes o el archivo subido, usa 'ventas_externas'.
    2. Usa siempre ILIKE para comparaciones de texto (ej. producto ILIKE '%cafe%').
    3. Responde ÚNICAMENTE con el código SQL, sin explicaciones.
    
    CONTEXTO:
    Fecha actual: {fechas['actual']}
    Pregunta: {question}
    """
    
    try:
        # EL TRUCO MAESTRO: Forzamos la api_version a 'v1' para saltar el error 404 de v1beta
        response = model.generate_content(
            prompt,
            request_options=RequestOptions(api_version='v1')
        )
        
        sql_raw = response.text.strip()
        # Limpieza de bloques de código markdown si la IA los incluye
        sql_match = re.search(r'SELECT.*', sql_raw, re.IGNORECASE | re.DOTALL)
        
        if sql_match:
            # Extraemos el SELECT y quitamos puntos y comas finales para evitar errores
            clean_sql = sql_match.group(0).replace('```sql', '').replace('```', '').split(';')[0].strip()
            return clean_sql, None
            
        return sql_raw, "Formato SQL no detectado"

    except Exception as e:
        print(f"DEBUG ERROR IA: {str(e)}")
        return None, f"Error en generación SQL: {str(e)}"

# --- 4. INTERPRETACIÓN DE RESULTADOS ---
def generate_ai_response(question, columns, data, sql_query, db_error):
    if not model: return "Error: IA no disponible."
    
    # Resumen de los datos para no saturar la memoria de la IA
    data_summary = f"Columnas: {columns}\nDatos obtenidos (muestra): {data[:15]}"
    if not data: data_summary = "La consulta no devolvió resultados en la base de datos."

    prompt_analisis = f"""
    Eres un Consultor de Negocios. Analiza los siguientes datos obtenidos de la base de datos:
    Pregunta original: {question}
    Datos: {data_summary}
    
    INSTRUCCIONES:
    1. Crea una tabla Markdown elegante con los resultados.
    2. Da una conclusión breve y profesional sobre lo que los datos muestran.
    """
    
    try:
        # También forzamos v1 aquí para asegurar consistencia
        response = model.generate_content(
            prompt_analisis,
            request_options=RequestOptions(api_version='v1')
        )
        return response.text
    except Exception as e:
        return f"Resultados directos: {data}. (Nota: Hubo un error al generar el análisis: {str(e)})"