# ai_analyzer.py (VERSIÓN DEFINITIVA - CORRECCIÓN 404 Y NAMEERROR)

from google import genai
from google.genai import types
import os
from datetime import datetime
import re 

# --- 1. CONFIGURACIÓN ---
API_KEY = os.environ.get("GEMINI_API_KEY") 
# Usamos el nombre corto para máxima compatibilidad con la SDK v1.0+
MODEL_NAME = 'gemini-1.5-flash' 

client = None
if API_KEY:
    try:
        client = genai.Client(api_key=API_KEY)
        print(f"INFO: Cliente Gemini ({MODEL_NAME}) inicializado correctamente.")
    except Exception as e:
        print(f"ERROR: No se pudo inicializar Gemini: {e}")

# --- 2. ESQUEMA DE LA BASE DE DATOS (Optimizado para PostgreSQL) ---
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
    if not client: 
        return None, "Error: Cliente Gemini no inicializado"
    
    fechas = get_fechas_analisis()
    
    # DEFINICIÓN DEL PROMPT (Solución al NameError)
    prompt = f"""
    Eres un Analista de Datos Senior experto en POSTGRESQL.
    Tu tarea es traducir la pregunta del usuario a una consulta SQL válida.

    --- REGLAS DE ORO ---
    1. Usa ILIKE para comparaciones de texto (ej: nombre_ciudad ILIKE '%Bogota%').
    2. Usa JOINs explícitos para conectar tablas.
    3. Retorna ÚNICAMENTE el código SQL SELECT, sin explicaciones.
    4. No uses bloques de código markdown (```sql).

    --- ESQUEMA ---
    {ESQUEMA_DB}

    --- CONTEXTO ---
    Fecha actual del sistema: {fechas['fecha_actual']}
    
    Pregunta del usuario: {question}
    {f'CORRECCIÓN DE ERROR PREVIO: {correction_context}' if correction_context else ''}
    """
    
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                system_instruction="Generar solo código SQL puro para PostgreSQL. No incluyas markdown ni texto adicional."
            )
        )
        
        # Limpieza de la respuesta para evitar errores de ejecución
        sql_text = response.text.strip()
        
        # Eliminar backticks de markdown si la IA los pone por error
        sql_text = re.sub(r'```(?:sql)?|```', '', sql_text).strip()
        
        # Asegurarnos de que empiece con SELECT
        sql_match = re.search(r'SELECT.*', sql_text, re.IGNORECASE | re.DOTALL)
        
        if sql_match:
            # Quitamos el punto y coma final para evitar conflictos en algunos drivers
            clean_sql = sql_match.group(0).split(';')[0].strip()
            return clean_sql, None
            
        return sql_text, "Formato SQL no reconocido"

    except Exception as e:
        return None, f"Error en generate_sql_query: {str(e)}"

# --- 5. INTERPRETACIÓN DE RESULTADOS ---
def generate_ai_response(question, columns, data, sql_query, db_error):
    if not client: 
        return "Error: IA fuera de línea."
    
    data_summary = f"Columnas: {columns}\nDatos obtenidos: {data[:20]}" 
    if not data: 
        data_summary = "La consulta no arrojó ningún resultado."

    prompt_analisis = f"""
    Eres un Consultor de Negocios de alto nivel. 
    Analiza los siguientes resultados de la base de datos para responder a la pregunta del usuario.

    Pregunta: {question}
    SQL Ejecutado: {sql_query}
    Resultados: {data_summary}
    
    Instrucciones:
    1. Responde de forma profesional y ejecutiva.
    2. Si hay datos, preséntalos en una tabla Markdown elegante.
    3. Si no hay datos, explica amablemente que no se encontraron registros.
    4. No menciones detalles técnicos como IDs internos.
    """
    
    try:
        response = client.models.generate_content(
            model=MODEL_NAME, 
            contents=prompt_analisis
        )
        return response.text
    except Exception as e:
        return f"Error en la interpretación de la IA: {e}"