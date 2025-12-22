# ai_analyzer.py (VERSIÓN PROFESIONAL CON DICCIONARIO DE SINÓNIMOS)

from google import genai
from google.genai import types
import os
from datetime import datetime
import re 

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

# --- 4. GENERACIÓN DE SQL CON DICCIONARIO DE SINÓNIMOS ---
def generate_sql_query(question, correction_context=None):
    if not client: return None, "Error de Cliente"
    
    fechas = get_fechas_analisis()
    
    # DICCIONARIO DE SINÓNIMOS Y REGLAS DE NEGOCIO
    LOGICA_NEGOCIO = """
    DICCIONARIO DE SINÓNIMOS (Mapeo de lenguaje natural a Columnas):
    1. 'Precio', 'Costo', 'Caro', 'Barato', 'Valor unitario' -> Usa siempre: Productos.precio
    2. 'Gasto total', 'Monto', 'Ingresos', 'Venta total' -> Usa siempre: Ventas.total
    3. 'Cuántos', 'Unidades', 'Volumen', 'Stock vendido' -> Usa siempre: DetalleVenta.cantidad
    4. 'Categoría', 'Tipo de producto', 'Línea' -> Usa siempre: Categorias.nombre_categoria
    5. 'Ubicación', 'Lugar', 'Donde' -> Usa siempre: Ciudades.nombre_ciudad o Sucursales.nombre_sucursal

    REGLAS DE SEGMENTACIÓN:
    - 'Clientes de Alto Valor': SUM(Ventas.total) > (SELECT AVG(total) * 2 FROM Ventas).
    - 'Productos estrella': Los más vendidos en DetalleVenta.
    - Búsqueda de nombres: Usa siempre LIKE '%texto%' para nombres de ciudades, productos o clientes.
    """

    prompt = f"""
    Eres un Analista de Datos Senior experto en SQLite. Traduce la pregunta a SQL.
    
    {LOGICA_NEGOCIO}

    --- ESQUEMA DE TABLAS ---
    {ESQUEMA_DB}

    --- CONTEXTO ---
    Fecha actual: {fechas['fecha_actual']}
    Pregunta: {question}
    {f'ERROR A CORREGIR: {correction_context}' if correction_context else ''}
    
    Instrucción: Genera estrictamente el código SQL SELECT. Si la pregunta requiere unir tablas, usa JOIN.
    """
    
    try:
        response = client.models.generate_content(
            model='models/gemini-1.5-flash', # Actualizado a la versión más reciente
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                system_instruction="Responde solo con la consulta SQL. Sin explicaciones ni bloques de código markdown."
            )
        )
        
        # Limpieza de la respuesta para obtener solo el SELECT
        clean_text = response.text.strip().replace('```sql', '').replace('```', '')
        sql_match = re.search(r'SELECT.*', clean_text, re.IGNORECASE | re.DOTALL)
        
        if sql_match:
            query = sql_match.group(0).split(';')[0].strip()
            return query, None
        return clean_text, "Error de formato SQL"

    except Exception as e:
        return None, str(e)

# --- 5. INTERPRETACIÓN ---
def generate_ai_response(question, columns, data, sql_query, db_error):
    if not client: return "Error de Cliente"
    
    data_summary = f"Columnas: {columns}\nDatos: {data[:20]}" 
    if not data: data_summary = "No se encontraron resultados."

    prompt = f"""
    Eres un Analista de Negocios Senior. Interpreta estos datos para un informe ejecutivo.
    
    Pregunta: {question}
    SQL Ejecutado: {sql_query}
    Resultados: {data_summary}
    
    Reglas de respuesta:
    1. Usa un tono muy profesional y ejecutivo.
    2. Si hay datos numéricos, relaciónalos con la pregunta (ej. 'El producto más caro es...').
    3. Si el resultado es una lista de categorías o ciudades con montos, nómbralos en la interpretación.
    4. Usa Markdown para tablas y negritas.
    """
    
    try:
        response = client.models.generate_content(model='models/gemini-1.5-flash', contents=prompt)
        return response.text
    except Exception as e:
        return f"Error en interpretación: {e}"