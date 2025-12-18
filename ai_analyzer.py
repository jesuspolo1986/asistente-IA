import google.generativeai as genai
import os
import time
from datetime import datetime

# --- 1. CONFIGURACIÓN ---
API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyAnfL9ZGSvmPI8iMfQPHuHtAjLWcC7mKsg") 
genai.configure(api_key=API_KEY)

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
    model = genai.GenerativeModel('gemini-1.5-flash')
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    
    prompt = f"Eres un experto en SQLite. Traduce a SQL SELECT: {question}. Esquema: {ESQUEMA_DB}. Hoy es: {fecha_hoy}. Responde SOLO el código SQL."

    for intento in range(3):
        try:
            response = model.generate_content(prompt)
            sql = response.text.strip().replace('```sql', '').replace('```', '').split(';')[0].strip()
            return sql, None
        except Exception as e:
            if "429" in str(e):
                time.sleep(10)
                continue
            return None, str(e)

# --- 4. INTERPRETACIÓN ---
def generate_ai_response(question, columns, data, sql_query, db_error):
    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = f"Analiza estos datos de ventas: {data}. Columnas: {columns}. Pregunta del usuario: {question}. Responde con una tabla Markdown y un consejo de negocio."
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error en interpretación: {e}"