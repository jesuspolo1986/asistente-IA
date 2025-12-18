import google.generativeai as genai
from google.generativeai.types import SafetySettingDict
import os
import time
from datetime import datetime

# --- 1. CONFIGURACIÓN FORZADA A V1 (ESTABLE) ---
API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyAnfL9ZGSvmPI8iMfQPHuHtAjLWcC7mKsg")

# Forzamos la configuración global
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
    # ESPECIFICAMOS EL MODELO COMPLETO PARA EVITAR RUTAS DINÁMICAS
    model = genai.GenerativeModel(model_name='models/gemini-1.5-flash')
    
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    prompt = f"Expert SQLite Translator. Schema: {ESQUEMA_DB}. Today: {fecha_hoy}. Task: Translate '{question}' to SQL. Response: SQL ONLY."

    for intento in range(2):
        try:
            # Usamos el método de generación estándar
            response = model.generate_content(prompt)
            sql = response.text.strip().replace('```sql', '').replace('```', '').split(';')[0].strip()
            return sql, None
        except Exception as e:
            if "404" in str(e):
                # Si falla, intentamos con la versión específica del modelo
                try:
                    model_alt = genai.GenerativeModel(model_name='gemini-1.5-flash')
                    r2 = model_alt.generate_content(prompt)
                    return r2.text.strip().replace('```sql', '').replace('```', '').split(';')[0].strip(), None
                except: pass
            time.sleep(2)
            continue
            
    return None, f"Error persistente en Google API: {e}"

# --- 4. INTERPRETACIÓN ---
def generate_ai_response(question, columns, data, sql_query, db_error):
    model = genai.GenerativeModel(model_name='models/gemini-1.5-flash')
    prompt = f"Analista: {data}. Columnas: {columns}. Pregunta: {question}. Responde con tabla Markdown."
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error en interpretación: {e}"