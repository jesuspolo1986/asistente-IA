import google.genai as genai
import os
import re
from datetime import datetime

API_KEY = os.environ.get("GEMINI_API_KEY")

if API_KEY:
    client = genai.Client(api_key=API_KEY)
    MODEL_NAME = "models/gemini-2.5-flash"   # más rápido y económico
    model = client.models.get(MODEL_NAME)
    print(f"INFO: Sistema vinculado al modelo: {MODEL_NAME}")
else:
    model = None
    print("ERROR: Clave API no detectada.")

ESQUEMA_DB = """
ventas_externas (
    fecha_venta TIMESTAMP, cliente TEXT, producto TEXT, 
    categoria TEXT, cantidad INT, precio_unitario DECIMAL, 
    total DECIMAL, sucursal TEXT
);
"""

def generate_sql_query(question, correction_context=None):
    if not model: 
        return None, "IA no configurada."
    
    prompt = f"""
Eres un experto en PostgreSQL. Genera SOLO el código SQL SELECT.
Esquema: {ESQUEMA_DB}
Pregunta: {question}
Instrucción: Usa ILIKE para textos y responde solo con el código.
"""
    try:
        response = model.generate_content(prompt)
        sql_raw = (response.text or "").strip()
        if not sql_raw:
            return None, "La IA no devolvió texto."
        
        sql_match = re.search(r'(SELECT|WITH).*', sql_raw, re.IGNORECASE | re.DOTALL)
        if sql_match:
            clean_sql = sql_match.group(0).replace('```sql', '').replace('```', '').split(';')[0].strip()
            return clean_sql, None
        return sql_raw, None
    except Exception as e:
        return None, f"Error en IA: {str(e)}"

def generate_ai_response(question, columns, data, sql_query, db_error):
    if not model: 
        return "IA desconectada."
    if db_error:
        return f"❌ Error de BD: {db_error}"
    
    preview = data[:5] if data else []
    data_summary = f"Columnas: {columns}\nDatos: {preview}" if preview else "Sin resultados."
    prompt = f"""
Actúa como consultor. Resume estos datos en una tabla Markdown elegante.
Pregunta: {question}
Datos: {data_summary}
"""
    try:
        response = model.generate_content(prompt)
        return response.text or "La IA no devolvió texto."
    except Exception as e:
        return f"Resultados: {data}. Error al analizar: {str(e)}"
