import google.generativeai as genai
import os
import time
from datetime import datetime

# --- CONFIGURACIÓN ---
API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyAnfL9ZGSvmPI8iMfQPHuHtAjLWcC7mKsg")
genai.configure(api_key=API_KEY)

ESQUEMA_DB = """
Ciudades (id_ciudad, nombre_ciudad, pais);
Categorias (id_categoria, nombre_categoria);
Sucursales (id_sucursal, nombre_sucursal, id_ciudad);
Clientes (id_cliente, nombre, apellido, edad, id_ciudad);
Productos (id_producto, nombre, precio, id_categoria);
Ventas (id_venta, id_cliente, id_sucursal, fecha_venta, total);
DetalleVenta (id_detalle, id_venta, id_producto, cantidad, subtotal);
"""

def generate_sql_query(question, correction_context=None):
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    prompt = f"Convierte a SQL para SQLite: {question}. Esquema: {ESQUEMA_DB}. Devuelve SOLO el codigo SQL, sin explicaciones ni comillas markdown."

    try:
        response = model.generate_content(prompt)
        # Limpieza extrema del SQL
        sql = response.text.strip().replace('```sql', '').replace('```', '').replace(';', '').strip()
        print(f"DEBUG SQL: {sql}") # Esto saldrá en tus logs de Render
        return sql, None
    except Exception as e:
        return None, str(e)

def generate_ai_response(question, columns, data, sql_query, db_error):
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    # Limitamos los datos para no saturar la API
    resumen_datos = str(data)[:500] 
    prompt = f"Analiza estos resultados: {resumen_datos}. Pregunta: {question}. Responde con una tabla Markdown breve."
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except:
        return "Consulta realizada con éxito, pero no pude generar el resumen."