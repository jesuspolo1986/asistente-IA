import google.generativeai as genai
import os
from datetime import datetime

# --- CONFIGURACIÓN ---
API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyAnfL9ZGSvmPI8iMfQPHuHtAjLWcC7mKsg")
genai.configure(api_key=API_KEY)

ESQUEMA_DB = "Tablas: Ciudades, Categorias, Sucursales, Clientes, Productos, Ventas, DetalleVenta."

def generate_sql_query(question, correction_context=None):
    # Usamos GEMINI-PRO: Es el modelo más estable para evitar errores 404
    model = genai.GenerativeModel('gemini-pro')
    
    prompt = f"SQLITE SQL ONLY. No text. Question: {question}. Schema: {ESQUEMA_DB}"

    try:
        response = model.generate_content(prompt)
        sql = response.text.strip().replace('```sql', '').replace('```', '').replace(';', '').strip()
        print(f"DEBUG SQL GENERADO: {sql}")
        return sql, None
    except Exception as e:
        return None, f"Error de API: {str(e)}"

def generate_ai_response(question, columns, data, sql_query, db_error):
    model = genai.GenerativeModel('gemini-pro')
    prompt = f"Data: {data}. Question: {question}. Answer with a table."
    try:
        response = model.generate_content(prompt)
        return response.text
    except:
        return "Consulta exitosa, pero error al resumir."