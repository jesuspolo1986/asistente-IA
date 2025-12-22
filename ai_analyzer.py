# ai_analyzer.py - VERSIÓN CORREGIDA PARA RENDER

from google import genai
from google.genai import types
import os
import re

# --- 1. CONFIGURACIÓN ---
API_KEY = os.environ.get("GEMINI_API_KEY")

# CAMBIO CLAVE: Algunas regiones de Render requieren el nombre corto 
# y otras el largo. La forma más segura en la nueva SDK es esta:
MODEL_NAME = "gemini-1.5-flash" 

client = None
if API_KEY:
    try:
        # Forzamos la inicialización limpia. 
        # La SDK google-genai por defecto usa la API v1 (Estable).
        client = genai.Client(api_key=API_KEY)
        print(f"INFO: Cliente Gemini inicializado exitosamente.")
    except Exception as e:
        print(f"ERROR: {e}")

# --- 4. GENERACIÓN DE SQL (Parte corregida) ---
def generate_sql_query(question, correction_context=None):
    if not client: return None, "Error: Cliente no inicializado"
    
    # ... (resto de tu código de fechas y esquema) ...

    try:
        # IMPORTANTE: No añadas 'models/' manualmente aquí. 
        # Deja que la SDK lo gestione.
        response = client.models.generate_content(
            model=MODEL_NAME, 
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                system_instruction="Responde solo con SQL SELECT para PostgreSQL."
            )
        )
        
        # Limpieza de la respuesta (Regex para evitar el 404 de formato)
        sql_text = response.text.strip()
        sql_match = re.search(r"SELECT.*", sql_text, re.IGNORECASE | re.DOTALL)
        
        if sql_match:
            # Eliminamos posibles backticks ```sql que Gemini a veces añade
            clean_sql = sql_match.group(0).replace("```sql", "").replace("```", "").strip()
            return clean_sql, None
        return sql_text, "Error de formato SQL"

    except Exception as e:
        # Este print te ayudará a ver la URL real en los logs de Render si vuelve a fallar
        print(f"DEBUG ERROR: {str(e)}")
        return None, str(e)