# ai_analyzer.py (VERSIÓN EXPERTA: ADAPTATIVA + PREDICTIVA)

from google import genai
from google.genai import types
import os
from datetime import datetime
import re 
from db_manager import execute_dynamic_query 

# --- 1. CONFIGURACIÓN ---
# Asegúrate de tener la variable de entorno GEMINI_API_KEY en Render
API_KEY = os.environ.get("GEMINI_API_KEY", "TU_CLAVE_AQUI") 

client = None
try:
    if API_KEY != "TU_CLAVE_AQUI":
        client = genai.Client(api_key=API_KEY)
        print("INFO: Cliente Gemini 2.0 inicializado correctamente.")
    else:
        print("ADVERTENCIA: API Key no configurada correctamente.")
except Exception as e:
    print(f"ERROR CRÍTICO: {e}")

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

# --- 3. GENERACIÓN DE SQL CON CAPA DE NEGOCIO AVANZADA ---
def generate_sql_query(question, correction_context=None):
    if not client: return None, "Error de Cliente"
    
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    
    # ESTA ES LA CAPA DE INTELIGENCIA QUE HACE TU CHATBOT ÚNICO
    LOGICA_NEGOCIO = """
    1. 'Clientes de Alto Valor': No uses montos fijos. Define como Alto Valor a quienes gastan más del DOBLE del promedio general.
       SQL Sugerido: ... WHERE id_cliente IN (SELECT id_cliente FROM Ventas GROUP BY id_cliente HAVING SUM(total) > (SELECT AVG(total) * 2 FROM Ventas))

    2. 'Proyecciones y Tendencias': Para proyectar el próximo mes, calcula el promedio de ventas de los últimos 3 meses y aplica la diferencia porcentual del último mes.
       SQL Sugerido: Usa STRFTIME('%Y-%m', fecha_venta) para agrupar por meses.

    3. 'Filtros de Sucursal/Ciudad': NUNCA filtres nombres directamente en la tabla Ventas. Haz JOIN con Sucursales o Ciudades y usa LIKE '%nombre%' para evitar errores de coincidencia exacta.

    4. 'Clientes en Riesgo': Clientes con menos compras que el promedio de frecuencia de la base de datos.
    """

    prompt = f"""
    Eres un Analista de Datos Senior experto en SQLite.
    Convierte la pregunta del usuario en una consulta SQL profesional.

    {LOGICA_NEGOCIO}

    --- ESQUEMA DE TABLAS ---
    {ESQUEMA_DB}

    --- CONTEXTO ---
    Fecha de hoy: {fecha_hoy}
    Pregunta: {question}
    {f'CONTEXTO DE ERROR ANTERIOR: {correction_context}' if correction_context else ''}
    
    Responde SOLO con el código SQL SELECT, sin explicaciones ni bloques de código markdown:
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            config=types.GenerateContentConfig(
                temperature=0.0,
                system_instruction="Genera código SQL SELECT puro. No incluyas ```sql ni texto extra."
            ),
            contents=prompt
        )
        
        sql_clean = response.text.strip().replace('```sql', '').replace('```', '').split(';')[0]
        return sql_clean, None

    except Exception as e:
        return None, str(e)

# --- 4. INTERPRETACIÓN DE RESULTADOS ---
def generate_ai_response(question, columns, data, sql_query, db_error):
    if not client: return "Error: IA no configurada."
    
    # Manejo de casos sin datos
    data_str = str(data[:15]) if data else "No se encontraron registros."
    
    prompt = f"""
    Eres un Analista de Negocios Senior. Tu trabajo es explicar resultados financieros.
    
    Pregunta original: {question}
    Columnas: {columns}
    Datos encontrados: {data_str}
    
    Instrucciones:
    1. Si hay datos, crea una tabla Markdown elegante.
    2. Realiza un breve análisis estratégico (insights).
    3. Si es una predicción, explica la base del cálculo (tendencia).
    4. Si no hay datos, explica de forma proactiva qué podría estar pasando.
    
    Responde con un tono ejecutivo y profesional:
    """
    
    try:
        response = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
        return response.text
    except Exception as e:
        return f"Error al interpretar resultados: {e}"