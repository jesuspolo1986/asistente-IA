# ai_analyzer.py (VERSIÓN RESILIENTE 404)

from google import genai
from google.genai import types
import os
from datetime import datetime
import time 
from db_manager import execute_dynamic_query 

# --- 1. CONFIGURACIÓN ---
API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyAnfL9ZGSvmPI8iMfQPHuHtAjLWcC7mKsg") 

client = None
try:
    client = genai.Client(api_key=API_KEY)
except Exception as e:
    print(f"Error inicial: {e}")

# --- 2. ESQUEMA ---
ESQUEMA_DB = """
CREATE TABLE Ciudades (id_ciudad INTEGER PRIMARY KEY, nombre_ciudad TEXT, pais TEXT);
CREATE TABLE Categorias (id_categoria INTEGER PRIMARY KEY, nombre_categoria TEXT);
CREATE TABLE Sucursales (id_sucursal INTEGER PRIMARY KEY, nombre_sucursal TEXT, id_ciudad INTEGER, FOREIGN KEY (id_ciudad) REFERENCES Ciudades (id_ciudad));
CREATE TABLE Clientes (id_cliente INTEGER PRIMARY KEY, nombre TEXT, apellido TEXT, edad INTEGER, id_ciudad INTEGER, FOREIGN KEY (id_ciudad) REFERENCES Ciudades (id_ciudad));
CREATE TABLE Productos (id_producto INTEGER PRIMARY KEY, nombre TEXT, precio REAL, id_categoria INTEGER, FOREIGN KEY (id_categoria) REFERENCES Categorias (id_categoria));
CREATE TABLE Ventas (id_venta INTEGER PRIMARY KEY, id_cliente INTEGER, id_sucursal INTEGER, fecha_venta TEXT, total REAL, FOREIGN KEY (id_cliente) REFERENCES Clientes (id_cliente), FOREIGN KEY (id_sucursal) REFERENCES Sucursales (id_sucursal));
CREATE TABLE DetalleVenta (id_detalle INTEGER PRIMARY KEY, id_venta INTEGER, id_producto INTEGER, cantidad INTEGER, subtotal REAL, FOREIGN KEY (id_venta) REFERENCES Ventas (id_venta), FOREIGN KEY (id_producto) REFERENCES Productos (id_producto));
"""

# --- 3. GENERACIÓN DE SQL ---
def generate_sql_query(question, correction_context=None):
    if not client: return None, "Cliente no listo"
    
    prompt = f"Genera SQL SELECT para SQLite: {question}. Esquema: {ESQUEMA_DB}. Responde solo el SQL."

    for i in range(3):
        try:
            # Quitamos el system_instruction para maximizar compatibilidad
            response = client.models.generate_content(
                model='gemini-1.5-flash', 
                contents=prompt
            )
            sql = response.text.strip().replace('```sql', '').replace('```', '').split(';')[0].strip()
            return sql, None
        except Exception as e:
            if "429" in str(e) and i < 2:
                time.sleep(10)
                continue
            return None, str(e)

# --- 4. INTERPRETACIÓN ---
def generate_ai_response(question, columns, data, sql_query, db_error):
    if not client: return "Error IA"
    prompt = f"Analiza estos datos: {data}. Columnas: {columns}. Pregunta: {question}. Crea tabla Markdown y da un consejo."
    
    try:
        response = client.models.generate_content(model='gemini-1.5-flash', contents=prompt)
        return response.text
    except Exception as e:
        return f"Error final: {e}"