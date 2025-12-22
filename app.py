from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
# CAMBIO CLAVE: Importamos get_db_connection en lugar de create_connection
from db_manager import get_db_connection, create_tables 
import supermercado 
import os

app = Flask(__name__)
CORS(app)

# --- INICIALIZACIÓN DE LA BASE DE DATOS ---
print("INFO: Intentando establecer conexión con PostgreSQL en Render...")

# 1. Crear la conexión Cloud (leera DATABASE_URL)
CONN = get_db_connection() 

# 2. Verificar y crear tablas en la nube
if CONN is not None:
    # En PostgreSQL, create_tables no necesita recibir la conexión 
    # porque la abre internamente, pero para mantener tu flujo:
    create_tables() 
    print("✅ INFO: Conexión a PostgreSQL exitosa. Infraestructura lista.")
else:
    print("❌ FATAL: No se pudo conectar a la base de datos Cloud. Verifica DATABASE_URL.")

# --- RUTAS ---

@app.route('/', methods=['GET'])
def serve_frontend():
    return send_from_directory('.', 'index.html')
from flask import request, redirect, flash
from data_uploader import procesar_y_cargar_excel

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return "No hay archivo"
    file = request.files['file']
    if file.filename == '':
        return "Archivo no seleccionado"
    
    if file:
        file_path = os.path.join("uploads", file.filename)
        if not os.path.exists("uploads"): os.makedirs("uploads")
        file.save(file_path)
        
        success, message = procesar_y_cargar_excel(file_path)
        return f"<h3>{message}</h3><a href='/'>Volver al Analista</a>"
@app.route('/api/consulta', methods=['POST'])
def handle_query():
    # Siempre verificamos si la conexión está activa
    # Nota: En apps de alto tráfico se recomienda abrir/cerrar conexión por consulta
    # pero para este analista, usaremos la global por ahora.
    
    global CONN
    if CONN is None or CONN.closed:
        CONN = get_db_connection()

    try:
        data = request.get_json()
        question = data.get('question', '').strip()
    except Exception:
        return jsonify({"status": "error", "error": "Formato JSON inválido."}), 400

    if not question:
        return jsonify({"status": "error", "error": "Pregunta vacía."}), 400

    print(f"[API] Procesando: {question}")
    
    try:
        # Enviamos CONN a la lógica de Gemini en supermercado.py
        response_text = supermercado.run_chat_analysis_api(CONN, question)
        
        status = "success"
        if response_text.startswith("ERROR") or response_text.startswith("ALERTA"):
            status = "failed"
        
        return jsonify({
            "status": status,
            "query": question,
            "response": response_text
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error", 
            "error": f"Error en el orquestador: {str(e)}"
        }), 500

if __name__ == '__main__':
    app.run(debug=False, port=int(os.environ.get('PORT', 5000)), host='0.0.0.0')
