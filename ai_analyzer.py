# ai_analyzer.py (SOLUCIÓN DEFINITIVA AL ERROR 404)

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
    print("INFO: Cliente Gemini configurado.")
except Exception as e:
    print(f"ERROR CONFIG: {e}")

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

# --- 3. GENERACIÓN DE SQL CON DOBLE INTENTO ---
def generate_sql_query(question, correction_context=None):
    if not client: return None, "Cliente no inicializado"
    
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    prompt = f"Como experto en SQLite, traduce a SQL SELECT: {question}. Esquema: {ESQUEMA_DB}. Hoy es: {fecha_hoy}. Solo devuelve el código SQL."

    # Lista de modelos a probar para evitar el error 404
    modelos_a_probar = ['gemini-1.5-flash-002', 'gemini-1.5-flash']

    for modelo in modelos_a_probar:
        for intento in range(2):
            try:
                response = client.models.generate_content(
                    model=modelo,
                    config=types.GenerateContentConfig(temperature=0.0),
                    contents=prompt
                )
                sql = response.text.strip().replace('```sql', '').replace('```', '').replace('\n', ' ')
                return sql.split(';')[0].strip(), None
            except Exception as e:
                if "429" in str(e):
                    time.sleep(10)
                    continue
                # Si es 404, saltará al siguiente modelo en la lista
                break 
    
    return None, "No se encontró un modelo compatible (404/Limit)"

# --- 4. INTERPRETACIÓN ---
def generate_ai_response(question, columns, data, sql_query, db_error):
    if not client: return "Error: IA desconectada."
    
    data_summary = str(data[:15]) if data else "Sin resultados."
    prompt = f"Pregunta: {question}. Datos: {data_summary}. Columnas: {columns}. Analiza y responde con tablas Markdown y un consejo."
    
    # Intentar con el modelo estable primero
    for modelo in ['gemini-1.5-flash-002', 'gemini-1.5-flash']:
        try:
            response = client.models.generate_content(model=modelo, contents=prompt)
            return response.text
        except:
            continue
            
    return "Error al procesar la respuesta con los modelos disponibles."