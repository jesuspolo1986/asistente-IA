import requests
import os
import json

# Configuración
API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyDw_9BgIjd-7bOnxzA2BqVLDSEyfrYMj6o")
# Forzamos la versión v1 (estable) en lugar de la v1beta
URL = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={API_KEY}"

def call_gemini_direct(prompt):
    headers = {'Content-Type': 'application/json'}
    data = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    
    response = requests.post(URL, headers=headers, json=data)
    
    if response.status_code == 200:
        result = response.json()
        return result['candidates'][0]['content']['parts'][0]['text']
    else:
        raise Exception(f"Error de Google ({response.status_code}): {response.text}")

def generate_sql_query(question, correction_context=None):
    prompt = f"SQLITE SQL ONLY. No markdown. Schema: Ventas, Productos, Clientes, Ciudades. Question: {question}"
    try:
        response_text = call_gemini_direct(prompt)
        sql = response_text.strip().replace('```sql', '').replace('```', '').replace(';', '').strip()
        return sql, None
    except Exception as e:
        return None, str(e)

def generate_ai_response(question, columns, data, sql_query, db_error):
    prompt = f"Data: {data}. Question: {question}. Responde con una tabla breve en español."
    try:
        return call_gemini_direct(prompt)
    except:
        return "Consulta exitosa, pero no se pudo generar el resumen."