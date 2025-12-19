import google.generativeai as genai
import os

# Configuración directa como en la versión de segmentación
API_KEY = os.environ.get("AIzaSyDw_9BgIjd-7bOnxzA2BqVLDSEyfrYMj6o")
genai.configure(api_key="AIzaSyDw_9BgIjd-7bOnxzA2BqVLDSEyfrYMj6o")

def generate_sql_query(question, correction_context=None):
    # Usamos el modelo estándar que no da problemas de ruta
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
    Eres un experto en SQLite.
    Esquema: Ventas, Productos, Clientes, Ciudades, Categorias, Sucursales, DetalleVenta.
    Pregunta: {question}
    Responde ÚNICAMENTE con el código SQL, sin bloques de texto ni comillas.
    """

    try:
        response = model.generate_content(prompt)
        sql = response.text.strip().replace('```sql', '').replace('```', '').replace(';', '').strip()
        return sql, None
    except Exception as e:
        return None, str(e)

def generate_ai_response(question, columns, data, sql_query, db_error):
    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = f"Analiza estos datos: {data}. Pregunta del usuario: {question}. Responde con una tabla breve en español."
    try:
        response = model.generate_content(prompt)
        return response.text
    except:
        return "Consulta exitosa, pero no se pudo generar el resumen."