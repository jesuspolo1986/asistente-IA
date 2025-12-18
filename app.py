# app.py (VERSIÓN OPTIMIZADA)

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from db_manager import create_connection, create_tables 
import supermercado 
import os
import atexit # Para cerrar la conexión limpiamente

app = Flask(__name__)
CORS(app)

# --- INICIALIZACIÓN ---
print("INFO: Iniciando Asistente IA...")
CONN = create_connection() 

if CONN is not None:
    create_tables(CONN)
    print("INFO: Base de datos lista y conectada.")
else:
    print("FATAL: Error al conectar con SQLite.")

# Cerrar conexión al apagar el servidor para evitar bloqueos en Render
@atexit.register
def close_db_connection():
    if CONN:
        CONN.close()
        print("INFO: Conexión a DB cerrada correctamente.")

# --- RUTAS ---

@app.route('/', methods=['GET'])
def serve_frontend():
    # Sirve el index.html desde la carpeta raíz
    return send_from_directory('.', 'index.html')

@app.route('/api/consulta', methods=['POST'])
def handle_query():
    if CONN is None:
        return jsonify({"status": "error", "error": "DB Desconectada"}), 500
    
    try:
        data = request.get_json()
        question = data.get('question', '').strip()
    except Exception:
        return jsonify({"status": "error", "error": "JSON Inválido"}), 400

    if not question:
        return jsonify({"status": "error", "error": "Pregunta vacía"}), 400

    print(f"[*] Procesando: {question}")
    
    try:
        # Aquí es donde ocurre la magia llamando a tu nuevo ai_analyzer
        response_text = supermercado.run_chat_analysis_api(CONN, question)
        
        status = "success"
        if "ERROR" in response_text.upper() or "ALERTA" in response_text.upper():
            status = "failed"
        
        return jsonify({
            "status": status,
            "query": question,
            "response": response_text
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, port=port, host='0.0.0.0')