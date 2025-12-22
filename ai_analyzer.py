from google import genai
from google.genai import types
import os
from datetime import datetime
import re 

# --- 1. CONFIGURACIÓN ---
API_KEY = os.environ.get("GEMINI_API_KEY") 
# Usamos el identificador estándar. La SDK se encarga del resto.
MODEL_NAME = 'gemini-1.5-flash' 

client = None
if API_KEY:
    try:
        # Inicialización optimizada para la SDK google-genai
        client = genai.Client(api_key=API_KEY)
        print(f"INFO: Cliente Gemini ({MODEL_NAME}) configurado correctamente.")
    except Exception as e:
        print(f"ERROR al inicializar Gemini: {e}")

# --- 2. ESQUEMA DE LA BASE DE DATOS ---
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
    if not client: return None, "Error: Cliente Gemini no inicializado"
    
    fechas = get_fechas_analisis()
    
    prompt = f"""
    Eres un Analista de Datos Senior experto en POSTGRESQL.
    Traduce la pregunta a una consulta SQL válida para PostgreSQL.

    --- REGLAS ---
    1. Usa ILIKE para búsquedas de texto (evita errores de mayúsculas).
    2. Retorna únicamente el código SQL, sin bloques de código ```sql ni explicaciones.
    3. Si el usuario pregunta por "clientes de alto valor", busca aquellos con ventas totales superiores al promedio.

    --- ESQUEMA ---
    {ESQUEMA_DB}

    --- CONTEXTO TEMPORAL ---
    Fecha actual: {fechas['fecha_actual']}
    
    Pregunta: {question}
    {f'CORRECCIÓN REQUERIDA: {correction_context}' if correction_context else ''}
    """
    
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                system_instruction="Generar solo código SQL SELECT puro para PostgreSQL."
            )
        )
        
        # Limpieza profunda de la respuesta
        raw_sql = response.text.strip()
        # Eliminar bloques de código markdown si la IA los incluye
        clean_sql = re.sub(r'```(?:sql)?|```', '', raw_sql).strip()
        # Extraer solo el SELECT en caso de que haya texto basura
        sql_match = re.search(r'SELECT.*', clean_sql, re.IGNORECASE | re.DOTALL)
        
        if sql_match:
            final_sql = sql_match.group(0).split(';')[0].strip()
            return final_sql, None
        return clean_sql, "Error de formato en la respuesta SQL"

    except Exception as e:
        return None, f"Error en generate_sql_query: {str(e)}"

# --- 5. INTERPRETACIÓN ---
def generate_ai_response(question, columns, data, sql_query, db_error):
    if not client: return "Error: Cliente Gemini no disponible."
    
    data_summary = f"Columnas: {columns}\nDatos: {data[:25]}" 
    if not data: data_summary = "No se encontraron registros en la base de datos."

    prompt = f"""
    Eres un Consultor Estratégico. Interpreta estos resultados de PostgreSQL.
    Pregunta: {question}
    SQL: {sql_query}
    Datos: {data_summary}
    
    Instrucciones:
    1. Responde con una tabla Markdown si hay datos.
    2. Da una conclusión ejecutiva breve.
    3. No menciones errores técnicos al usuario.
    """
    
    try:
        response = client.models.generate_content(
            model=MODEL_NAME, 
            contents=prompt
        )
        return response.text
    except Exception as e:
        return f"Error al generar interpretación: {e}"