import google.generativeai as genai
import os
import re
from datetime import datetime

# --- 1. CONFIGURACIÓN DE SEGURIDAD ---
API_KEY = os.environ.get("GEMINI_API_KEY")

model = None

def _init_model():
    global model
    if not API_KEY:
        print("ERROR: No se detectó GEMINI_API_KEY en las variables de entorno.")
        return

    genai.configure(api_key=API_KEY)

    # Validar y elegir modelo disponible
    try:
        available = [m.name for m in genai.list_models()]
    except Exception as e:
        print(f"ERROR: No se pudo listar modelos: {e}")
        return

    preferred = "models/gemini-1.5-flash-latest"
    fallback  = "models/gemini-1.5-pro-latest"

    chosen = preferred if preferred in available else (fallback if fallback in available else None)

    if not chosen:
        print("ERROR: Ningún modelo Gemini 1.5 disponible (flash/pro).")
        return

    # Inicializa el modelo estable
    model = genai.GenerativeModel(chosen)
    print(f"INFO: Sistema AI Pro Analyst inicializado con {chosen}.")

_init_model()

# --- 2. ESQUEMA DE DATOS ---
ESQUEMA_DB = """
-- TABLA DE EXCEL (Cargas externas)
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

-- TABLAS DEL SISTEMA (Relacionales)
Ciudades (id_ciudad INT PRIMARY KEY, nombre_ciudad TEXT);
Categorias (id_categoria INT PRIMARY KEY, nombre_categoria TEXT);
Sucursales (id_sucursal INT PRIMARY KEY, nombre_sucursal TEXT, id_ciudad INT);
Clientes (id_cliente INT PRIMARY KEY, nombre TEXT, apellido TEXT);
Productos (id_producto SERIAL PRIMARY KEY, nombre TEXT, precio DECIMAL);
Ventas (id_venta SERIAL PRIMARY KEY, id_cliente INT, total DECIMAL);
"""

# --- 3. GENERACIÓN DE SQL ---
def generate_sql_query(question, correction_context=None):
    if not model:
        return None, "Error: IA no configurada."

    fechas = {"actual": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

    prompt = f"""
Eres un Analista de Datos Senior especializado en PostgreSQL.
Traduce la pregunta del usuario a una consulta SQL SELECT válida.

ESQUEMA DISPONIBLE:
{ESQUEMA_DB}

REGLAS:
1. Si la pregunta es sobre ventas recientes o el archivo subido, usa la tabla 'ventas_externas'.
2. Usa siempre ILIKE para comparaciones de texto (ej. producto ILIKE '%cafe%').
3. Responde ÚNICAMENTE con el código SQL, sin explicaciones ni comentarios.
4. Si la consulta requiere agregaciones, incluye alias claros para columnas.

CONTEXTO:
Fecha actual: {fechas['actual']}
Pregunta: {question}
{f"Nota de corrección: {correction_context}" if correction_context else ""}
"""

    try:
        response = model.generate_content(prompt)
        sql_raw = (response.text or "").strip()

        # Extraer SELECT o WITH completo
        sql_match = re.search(r'(WITH|SELECT).*', sql_raw, re.IGNORECASE | re.DOTALL)
        if not sql_match:
            return sql_raw, "Formato SQL no detectado"

        clean_sql = sql_match.group(0)
        # Remover posibles fences Markdown y cortar en el primer ';'
        clean_sql = clean_sql.replace('```sql', '').replace('```', '').strip()
        if ';' in clean_sql:
            clean_sql = clean_sql.split(';')[0].strip()

        # Validación básica de seguridad para evitar comandos peligrosos
        forbidden = ["drop", "delete", "truncate", "update", "alter"]
        if any(w in clean_sql.lower() for w in forbidden):
            return None, "Consulta bloqueada por seguridad (comando no permitido)."

        print(f"[AI SQL] {clean_sql}")
        return clean_sql, None

    except Exception as e:
        print(f"DEBUG ERROR IA (SQL): {str(e)}")
        return None, f"Error en generación SQL: {str(e)}"

# --- 4. INTERPRETACIÓN DE RESULTADOS ---
def generate_ai_response(question, columns, data, sql_query, db_error):
    if not model:
        return "Error: IA no disponible."

    if db_error:
        return f"Consulta: `{sql_query}`.\nError de BD: {db_error}"

    # Resumen controlado para no saturar contexto
    preview_rows = data[:15] if data else []
    table_md = ""
    if columns and preview_rows:
        # Construir tabla Markdown simple
        header = "| " + " | ".join(columns) + " |"
        sep = "| " + " | ".join(["---"] * len(columns)) + " |"
        lines = [header, sep]
        for row in preview_rows:
            cells = [str(c) for c in row]
            lines.append("| " + " | ".join(cells) + " |")
        table_md = "\n".join(lines)
    else:
        table_md = "No hubo resultados para la consulta."

    prompt_analisis = f"""
Eres un Consultor de Negocios. Analiza los datos y redacta una interpretación ejecutiva.

Pregunta original: {question}

Resultados (muestra):
{table_md}

Instrucciones:
1. Presenta insights claros, breves y accionables (máximo 4 puntos).
2. Señala posibles siguientes pasos o métricas relevantes si aplica.
3. Mantén tono profesional y preciso.
"""

    try:
        response = model.generate_content(prompt_analisis)
        return response.text or table_md
    except Exception as e:
        return f"{table_md}\n\nNota: Hubo un error al generar el análisis: {str(e)}"
