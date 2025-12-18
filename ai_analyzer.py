# ai_analyzer.py (VERSIÓN PROFESIONAL CON SEGMENTACIÓN)

from google import genai
from google.genai import types
import os
from datetime import datetime, timedelta
import re 
from db_manager import execute_dynamic_query, main_db_setup 

# --- 1. CONFIGURACIÓN ---
API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_FALLBACK_API_KEY_HERE") 

client = None
try:
    if API_KEY != "YOUR_FALLBACK_API_KEY_HERE":
        client = genai.Client(api_key=API_KEY)
        print("INFO: Cliente Gemini inicializado correctamente.")
    else:
        print("ADVERTENCIA: Usando clave de API de fallback.")
except Exception as e:
    print(f"ERROR CRÍTICO: {e}")
    client = None

# --- 2. ESQUEMA DE LA BASE DE DATOS ---
ESQUEMA_DB = """
CREATE TABLE Ciudades (id_ciudad INTEGER PRIMARY KEY, nombre_ciudad TEXT, pais TEXT);
CREATE TABLE Categorias (id_categoria INTEGER PRIMARY KEY, nombre_categoria TEXT);
CREATE TABLE Sucursales (id_sucursal INTEGER PRIMARY KEY, nombre_sucursal TEXT, id_ciudad INTEGER, FOREIGN KEY (id_ciudad) REFERENCES Ciudades (id_ciudad));
CREATE TABLE Clientes (id_cliente INTEGER PRIMARY KEY, nombre TEXT, apellido TEXT, edad INTEGER, id_ciudad INTEGER, FOREIGN KEY (id_ciudad) REFERENCES Ciudades (id_ciudad));
CREATE TABLE Productos (id_producto INTEGER PRIMARY KEY, nombre TEXT, precio REAL, id_categoria INTEGER, FOREIGN KEY (id_categoria) REFERENCES Categorias (id_categoria));
CREATE TABLE Ventas (id_venta INTEGER PRIMARY KEY, id_cliente INTEGER, id_sucursal INTEGER, fecha_venta TEXT, total REAL, FOREIGN KEY (id_cliente) REFERENCES Clientes (id_cliente), FOREIGN KEY (id_sucursal) REFERENCES Sucursales (id_sucursal));
CREATE TABLE DetalleVenta (id_detalle INTEGER PRIMARY KEY, id_venta INTEGER, id_producto INTEGER, cantidad INTEGER, subtotal REAL, FOREIGN KEY (id_venta) REFERENCES Ventas (id_venta), FOREIGN KEY (id_producto) REFERENCES Productos (id_producto));
"""

# --- 3. UTILIDADES ---
def get_fechas_analisis():
    now = datetime.now()
    return {
        "fecha_actual": now.strftime("%Y-%m-%d %H:%M:%S"),
        "mes_actual": now.strftime("%Y-%m"),
    }

# --- 4. GENERACIÓN DE SQL CON CAPA DE NEGOCIO ---
def generate_sql_query(question, correction_context=None):
    if not client: return None, "Error de Cliente"
    
    fechas = get_fechas_analisis()
    
    # REGLAS DE NEGOCIO INYECTADAS
    LOGICA_NEGOCIO = """
    --- REGLAS DE SEGMENTACIÓN (CRÍTICO) ---
    1. 'Clientes de Alto Valor': Clientes cuyo SUM(Ventas.total) es mayor a 500.
    2. 'Clientes en Riesgo': Clientes con menos de 3 registros en la tabla Ventas.
    3. 'Sucursales': Los nombres exactos son 'Norte', 'Sur', 'Este', 'Oeste', 'Centro'. Si el usuario dice 'Sucursal Norte', busca 'Norte'.
    4. 'Categorías': Los nombres son 'Carnes', 'Lácteos', 'Bebidas', 'Limpieza', 'Panadería'.
    
    --- INSTRUCCIÓN TÉCNICA ---
    - Para 'Alto Valor', usa: WHERE id_cliente IN (SELECT id_cliente FROM Ventas GROUP BY id_cliente HAVING SUM(total) > 500)
    - Para 'Riesgo', usa: WHERE id_cliente IN (SELECT id_cliente FROM Ventas GROUP BY id_cliente HAVING COUNT(id_venta) < 3)
    """

    prompt = f"""
    Eres un Analista de Datos Senior. Traduce la pregunta a SQL para SQLite.
    
    {LOGICA_NEGOCIO}

    --- ESQUEMA ---
    {ESQUEMA_DB}

    --- CONTEXTO TEMPORAL ---
    Fecha actual: {fechas['fecha_actual']}
    
    Pregunta: {question}
    {f'ERROR ANTERIOR: {correction_context}' if correction_context else ''}
    
    Genera SOLO el código SQL SELECT:
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                system_instruction="Responde estrictamente con SQL SELECT. No expliques."
            )
        )
        
        sql_query = re.search(r'SELECT.*', response.text.strip(), re.IGNORECASE | re.DOTALL)
        return (sql_query.group(0).split(';')[0].strip(), None) if sql_query else (response.text, "Error de formato")

    except Exception as e:
        return None, str(e)

# --- 5. INTERPRETACIÓN ---
def generate_ai_response(question, columns, data, sql_query, db_error):
    if not client: return "Error de Cliente"
    
    data_summary = f"Columnas: {columns}\nDatos: {data[:20]}" # Enviamos top 20 para ahorrar tokens
    if not data: data_summary = "No se encontraron resultados para esta consulta."

    prompt = f"""
    Eres un Analista de Negocios. Interpreta estos resultados de la base de datos.
    Pregunta del usuario: {question}
    Resultados: {data_summary}
    
    Instrucciones:
    1. Si hay datos, preséntalos en una tabla Markdown elegante.
    2. Responde de forma muy profesional, como un consultor.
    3. Si no hay datos, explica que no hay registros que cumplan con los criterios de ese segmento.
    """
    
    try:
        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        return response.text
    except Exception as e:
        return f"Error en interpretación: {e}"