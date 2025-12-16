# app.py (Servidor Flask API para el Analista Conversacional)

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
# Importar solo las funciones de conexión necesarias y el módulo
from db_manager import create_connection, create_tables 
import supermercado # Contiene run_chat_analysis_api
import os

# --- INICIALIZACIÓN DE LA APLICACIÓN ---
app = Flask(__name__)
CORS(app)

# --- CONFIGURACIÓN DE LA BASE DE DATOS (Solución de Estabilidad Crítica) ---
# Usamos la conexión ligera para evitar el fallo SIGKILL en Render.
print("INFO: Intentando establecer una conexión ligera a la base de datos...")

# 1. Crear la conexión al archivo existente (supermercado.db)
CONN = create_connection() 

# 2. Asegurarse de que las tablas existan (CREATE IF NOT EXISTS)
if CONN is not None:
    create_tables(CONN)
    print("INFO: Conexión a la DB exitosa. Tablas verificadas.")
else:
    print("FATAL: No se pudo establecer la conexión a la base de datos (SQLite).")


# --- RUTAS DE LA APLICACIÓN ---

# 1. RUTA PRINCIPAL (/) - Sirve el Frontend
@app.route('/', methods=['GET'])
def serve_frontend():
    """
    Sirve el archivo index.html (frontend) en la ruta raíz (/).
    Esto soluciona el problema de que el celular solo veía el mensaje "Activo".
    """
    # Asume que index.html está en la misma carpeta que app.py
    return send_from_directory('.', 'index.html')


# 2. RUTA DE LA API (/api/consulta) - Maneja la Lógica de la IA
@app.route('/api/consulta', methods=['POST'])
def handle_query():
    """
    Ruta principal para procesar las preguntas del usuario (NL2SQL). 
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
    
    # 3. Llamada al Orquestador Principal (Gemini)
    try:
        # La función run_chat_analysis_api llama a Gemini, obtiene el SQL, lo ejecuta y analiza el resultado.
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
        # Error inesperado durante el procesamiento (ej. fallo de la API de Gemini)
        return jsonify({
            "status": "error", 
            "error": f"Error interno del servidor al procesar la consulta: {str(e)}"
        }), 500


if __name__ == '__main__':
    # Usamos Gunicorn para producción, pero Flask para desarrollo local
    print("Servidor Flask iniciado en modo desarrollo.")
    # Asegúrate de que tu ambiente local tenga la variable PORT o usará 5000
    app.run(debug=True, port=os.environ.get('PORT', 5000), host='0.0.0.0')