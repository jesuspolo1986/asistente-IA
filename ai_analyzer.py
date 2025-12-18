# ai_analyzer.py (VERSIÓN FINAL RESILIENTE)

from google import genai
from google.genai import types
import os
from datetime import datetime
import re 
import time 
from db_manager import execute_dynamic_query 

# --- 1. CONFIGURACIÓN ---
# Prioriza la variable de entorno de Render, si no, usa tu nueva Key directamente
API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyAnfL9ZGSvmPI8iMfQPHuHtAjLWcC7mKsg") 

client = None
try:
    # Inicialización limpia para el SDK google-genai
    client = genai.Client(api_key=API_KEY)
    print("INFO: Cliente Gemini 1.5 Flash conectado correctamente.")
except Exception as e:
    print(f"ERROR DE CONFIGURACIÓN: {e}")

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

# --- 3. GENERACIÓN DE SQL ---
def generate_sql_query(question, correction_context=None):
    if not client: return None, "Cliente no inicializado"
    
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    LOGICA_NEGOCIO = """
    1. 'Alto Valor': Ventas totales por cliente > (promedio general * 2).
    2. 'Proyección': Agrupar por mes, calcular tendencia y sumar al último mes.
    3. 'Nombres': Usar JOIN y LIKE para ciudades/sucursales.
    """

    prompt = f"Como experto en SQLite, traduce: {question}. Esquema: {ESQUEMA_DB}. Hoy: {fecha_hoy}. Reglas: {LOGICA_NEGOCIO}"

    for intento in range(3):
        try:
            # Nombre de modelo simple para evitar Error 404
            response = client.models.generate_content(
                model='gemini-1.5-flash',
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    system_instruction="Responde solo con el código SQL SELECT, sin texto adicional."
                ),
                contents=prompt
            )
            # Limpieza de la respuesta
            sql = response.text.strip().replace('```sql', '').replace('```', '').split(';')[0].strip()
            return sql, None
        except Exception as e:
            if "429" in str(e) and intento < 2:
                time.sleep(12) # Pausa por cuota
                continue
            return None, f"Error en generación: {e}"

# --- 4. INTERPRETACIÓN ---
def generate_ai_response(question, columns, data, sql_query, db_error):
    if not client: return "Error: IA no disponible."
    
    data_resumen = str(data[:10]) if data else "No hay datos."
    prompt = f"Analiza para el gerente: {question}. Datos: {data_resumen}. Columnas: {columns}. Presenta en tabla Markdown y da un consejo estratégico."
    
    for intento in range(3):
        try:
            response = client.models.generate_content(
                model='gemini-1.5-flash',
                contents=prompt
            )
            return response.text
        except Exception as e:
            if "429" in str(e) and intento < 2:
                time.sleep(12)
                continue
            return f"Error en interpretación: {e}"