# ai_analyzer.py (VERSIÓN ANTIBLOQUEO Y PREDICTIVA)

from google import genai
from google.genai import types
import os
from datetime import datetime
import re 
import time 
from db_manager import execute_dynamic_query 

# --- 1. CONFIGURACIÓN ---
# --- 1. CONFIGURACIÓN ---
# Aquí "GEMINI_API_KEY" es el nombre que pusiste en Render
API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyAnfL9ZGSvmPI8iMfQPHuHtAjLWcC7mKsg") 

client = None
try:
    # Si la variable de entorno existe, la usa. Si no, usa el fallback (tu nueva llave)
    client = genai.Client(api_key=API_KEY)
    print("INFO: Cliente Gemini inicializado (Modo Resiliente).")
except Exception as e:
    print(f"ERROR: {e}")

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

# --- 3. GENERACIÓN DE SQL CON REINTENTOS ---
def generate_sql_query(question, correction_context=None):
    if not client: return None, "Error de Cliente"
    
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    LOGICA_NEGOCIO = """
    1. 'Alto Valor': Gasto > (promedio * 2).
    2. 'Proyección': Calcula tendencia mensual y proyecta el mes siguiente.
    3. 'Filtros': Siempre usa JOIN para nombres de ciudades o sucursales.
    """

    prompt = f"SQL Expert: Convierte a SQLite: {question}. Esquema: {ESQUEMA_DB}. Hoy: {fecha_hoy}. Reglas: {LOGICA_NEGOCIO}"

    for intento in range(3):
        try:
            response = client.models.generate_content(
                model='gemini-1.5-flash-latest',
                config=types.GenerateContentConfig(temperature=0.0, system_instruction="Solo SQL SELECT puro."),
                contents=prompt
            )
            # Limpieza profunda del SQL
            sql = response.text.strip().replace('```sql', '').replace('```', '').replace('\n', ' ')
            sql = sql.split(';')[0].strip()
            return sql, None
        except Exception as e:
            if "429" in str(e) and intento < 2:
                time.sleep(10) # Espera 10 segundos si la cuota se agota
                continue
            return None, str(e)

# --- 4. INTERPRETACIÓN ---
def generate_ai_response(question, columns, data, sql_query, db_error):
    if not client: return "Error de configuración de IA."
    
    data_summary = str(data[:15]) if data else "Sin resultados."
    prompt = f"Analista Pro: Explica estos datos: {data_summary} para la pregunta: {question}. Usa tablas Markdown y da un consejo de negocio."
    
    for intento in range(3):
        try:
            response = client.models.generate_content(model='gemini-1.5-flash', contents=prompt)
            return response.text
        except Exception as e:
            if "429" in str(e) and intento < 2:
                time.sleep(10)
                continue
            return f"Error en interpretación: {e}"