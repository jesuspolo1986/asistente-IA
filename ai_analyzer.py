import google.generativeai as genai
import os
import re
from datetime import datetime

# --- 1. CONFIGURACIÓN MANUAL DE API ---
API_KEY = os.environ.get("GEMINI_API_KEY")

# Forzamos la configuración para evitar el error 404 de v1beta
if API_KEY:
    genai.configure(api_key=API_KEY)
    # Inicializamos el modelo de forma explícita
    model = genai.GenerativeModel(model_name='gemini-1.5-flash')
    print("INFO: Sistema de IA reconectado exitosamente.")
else:
    model = None
    print("ERROR: Clave API no detectada.")

# --- 2. ESQUEMA DE LA BASE DE DATOS ---
ESQUEMA_DB = """
-- Tabla Principal de Excel (Donde están tus 65 registros)
ventas_externas (
    fecha_venta TIMESTAMP, 
    cliente TEXT, 
    producto TEXT, 
    categoria TEXT, 
    cantidad INT, 
    precio_unitario DECIMAL, 
    total DECIMAL, 
    sucursal TEXT
);
"""

# --- 3. GENERACIÓN DE SQL ---
def generate_sql_query(question, correction_context=None):
    if not model: return None, "IA no configurada"
    
    prompt = f"""
    Eres un Analista PostgreSQL. Genera SOLO el código SQL para esta pregunta:
    Pregunta: {question}
    Esquema: {ESQUEMA_DB}
    Importante: Usa ILIKE para textos. Responde solo con el SELECT.
    """
    
    try:
        # Usamos generate_content que es la llamada más estable
        response = model.generate_content(prompt)
        sql_raw = response.text.strip()
        
        # Limpieza de código markdown
        sql_query = re.search(r'SELECT.*', sql_raw, re.IGNORECASE | re.DOTALL)
        if sql_query:
            return sql_query.group(0).replace('```sql', '').replace('```', '').split(';')[0].strip(), None
        return sql_raw, None
    except Exception as e:
        return None, f"Error en IA: {str(e)}"

# --- 4. INTERPRETACIÓN ---
def generate_ai_response(question, columns, data, sql_query, db_error):
    if not model: return "IA desconectada."
    
    data_summary = f"Resultados: {data[:10]}"
    prompt = f"Actúa como analista. Resume estos datos en una tabla markdown: {data_summary}. Pregunta original: {question}"
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error al interpretar: {e}"