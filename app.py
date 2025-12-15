# app.py (Servidor Flask API para el Analista Conversacional)

from flask import Flask, request, jsonify
# Importar solo las funciones de conexión necesarias y el módulo
from db_manager import create_connection, create_tables 
import db_manager 
import supermercado # Contiene run_chat_analysis_api
from flask_cors import CORS
import os

# --- INICIALIZACIÓN DE LA APLICACIÓN ---
app = Flask(__name__)
CORS(app)

# --- SOLUCIÓN CRÍTICA PARA EL ERROR DE MEMORIA (SIGKILL) ---
# Se utiliza la función simple de conexión y creación de tablas.
# NO se llama a main_db_setup() que internamente podría haber llamado a seed_data().

print("INFO: Intentando establecer una conexión ligera a la base de datos...")

# 1. Crear la conexión al archivo existente (supermercado.db)
CONN = create_connection() 

# 2. Asegurarse de que las tablas existan (CREATE IF NOT EXISTS)
if CONN is not None:
    create_tables(CONN)
    print("INFO: Conexión a la DB exitosa. Tablas verificadas.")


if CONN is None:
    print("FATAL: No se pudo establecer la conexión a la base de datos (SQLite).")


# --- RUTAS DE LA API ---

@app.route('/', methods=['GET'])
def home():
    """Ruta de salud simple."""
    return "Analista Conversacional (Gemini AI) API v3.0 está ACTIVO.", 200

@app.route('/api/consulta', methods=['POST'])
def handle_query():
    """
    Ruta principal para procesar las preguntas del usuario. 
    Espera JSON: {"question": "..."}
    """
    
    # 1. Validación de la Conexión
    if CONN is None:
        return jsonify({
            "status": "error",
            "error": "Error 500: La conexión a la base de datos es nula. Revise la inicialización."
        }), 500
    
    # 2. Extracción y Validación de la Pregunta
    try:
        data = request.get_json()
        question = data.get('question', '').strip()
    except Exception:
        return jsonify({"status": "error", "error": "Formato de solicitud JSON inválido."}), 400

    if not question:
        return jsonify({"status": "error", "error": "Por favor, provea una pregunta válida."}), 400

    print(f"\n[API RECIBIDA] Pregunta: {question}")
    
    # 3. Llamada al Orquestador Principal
    try:
        # Usamos la función optimizada para la API (devuelve el texto)
        # Nota: La función run_chat_analysis_api debe estar en el archivo supermercado.py o ai_analyzer.py (si lo renombraste)
        response_text = supermercado.run_chat_analysis_api(CONN, question)
        
        # Determinamos el estado basado en si la respuesta contiene un error crítico
        status = "success"
        if response_text.startswith("ERROR") or response_text.startswith("ALERTA"):
            status = "failed"
        
        return jsonify({
            "status": status,
            "query": question,
            "response": response_text
        }), 200

    except Exception as e:
        # Error inesperado durante el procesamiento
        return jsonify({
            "status": "error", 
            "error": f"Error interno del servidor al procesar la consulta: {str(e)}"
        }), 500


if __name__ == '__main__':
    # Usamos Gunicorn para producción, pero Flask para desarrollo local
    print("Servidor Flask iniciado en modo desarrollo.")
    # Asegúrate de que tu ambiente local tenga la variable PORT o usará 5000
    app.run(debug=True, port=os.environ.get('PORT', 5000), host='0.0.0.0')