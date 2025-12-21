# app.py (Servidor Flask API para el Analista Conversacional)

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from db_manager import create_connection, create_tables 
import supermercado  # Importamos tu lógica de Gemini
import os
import pandas as pd
import io

# --- INICIALIZACIÓN DE LA APLICACIÓN ---
app = Flask(__name__)
CORS(app)

# --- CONFIGURACIÓN DE LA BASE DE DATOS ---
print("INFO: Iniciando conexión a la base de datos...")
CONN = create_connection() 

if CONN is not None:
    create_tables(CONN)
    print("INFO: Conexión a la DB exitosa.")
else:
    print("FATAL: No se pudo conectar a SQLite.")

# --- RUTAS ---

@app.route('/', methods=['GET'])
def serve_frontend():
    return send_from_directory('.', 'index.html')

@app.route('/api/consulta', methods=['POST'])
def handle_query():
    if CONN is None:
        return jsonify({"status": "error", "error": "DB Connection Null"}), 500
    
    try:
        data = request.get_json()
        question = data.get('question', '').strip()
    except Exception:
        return jsonify({"status": "error", "error": "JSON inválido"}), 400

    if not question:
        return jsonify({"status": "error", "error": "Pregunta vacía"}), 400

    try:
        # Usamos la función que ya tienes en supermercado.py
        response_text = supermercado.run_chat_analysis_api(CONN, question)
        status = "success" if not (response_text.startswith("ERROR") or response_text.startswith("ALERTA")) else "failed"
        
        return jsonify({
            "status": status,
            "query": question,
            "response": response_text
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

# --- RUTA PARA CARGAR EXCEL (CORREGIDA) ---
@app.route('/api/upload_excel', methods=['POST'])
def upload_excel():
    if 'file' not in request.files:
        return jsonify({"status": "error", "response": "No se seleccionó ningún archivo"})
    
    file = request.files['file']
    
    try:
        # 1. Leer el archivo según su extensión
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
        
        # 2. Preparar el resumen para Gemini
        columnas = df.columns.tolist()
        resumen = df.head(5).to_string()
        
        prompt = (
            f"Actúa como un experto Analista de Datos. El usuario ha subido un archivo con las siguientes columnas: {columnas}.\n"
            f"Aquí tienes una muestra de los datos:\n{resumen}\n\n"
            "Por favor, explica de forma breve qué información contiene este archivo y qué 3 preguntas interesantes "
            "podría hacerte el usuario sobre estos datos para analizar el negocio."
        )
        
        # 3. LLAMADA CORREGIDA: Usamos el modelo que ya está configurado en supermercado.py
        # Accedemos a supermercado.model porque ahí es donde hiciste genai.GenerativeModel
        response = supermercado.model.generate_content(prompt)
        
        return jsonify({
            "status": "success", 
            "response": f"📊 **Archivo cargado correctamente.**\n\n{response.text}"
        })
    except Exception as e:
        print(f"Error en upload_excel: {str(e)}")
        return jsonify({"status": "error", "response": f"Error al procesar: {str(e)}"})

if __name__ == '__main__':
    app.run(debug=True, port=os.environ.get('PORT', 5000), host='0.0.0.0')