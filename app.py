import os
from flask import Flask, jsonify, request, send_from_directory, redirect
from flask_cors import CORS

# Importaciones de tus módulos personalizados
from db_manager import get_db_connection, create_tables 
from data_uploader import procesar_y_cargar_excel
import ai_analyzer # Asegúrate de que este es el nombre de tu archivo de IA

app = Flask(__name__)
CORS(app)

# --- INICIALIZACIÓN ---
# Creamos la carpeta de subidas al arrancar
if not os.path.exists("uploads"):
    os.makedirs("uploads")

print("INFO: Iniciando infraestructura en Render...")
create_tables() 

# --- RUTAS DE NAVEGACIÓN ---

@app.route('/', methods=['GET'])
def serve_frontend():
    return send_from_directory('.', 'index.html')

# --- RUTA DE CARGA DE EXCEL ---

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return "No se encontró la parte del archivo en la solicitud."
    
    file = request.files['file']
    if file.filename == '':
        return "No seleccionaste ningún archivo."
    
    if file:
        file_path = os.path.join("uploads", file.filename)
        file.save(file_path)
        
        # Llamamos al procesador de Excel que usa SQLAlchemy
        success, message = procesar_y_cargar_excel(file_path)
        
        # Eliminamos el archivo temporal después de procesarlo para no llenar el disco
        if os.path.exists(file_path):
            os.remove(file_path)
            
        # Retornamos un mensaje sencillo y un botón para volver
        color = "green" if success else "red"
        return f"""
        <div style="font-family:sans-serif; text-align:center; margin-top:50px;">
            <h3 style="color:{color};">{message}</h3>
            <a href="/" style="text-decoration:none; background:#1e3a8a; color:white; padding:10px 20px; border-radius:5px;">Volver al Analista</a>
        </div>
        """

# --- RUTA DEL ANALISTA (CHAT) ---
# Cambiamos /api/consulta a /ask para que coincida con tu index.html

@app.route('/ask', methods=['POST'])
def handle_query():
    try:
        data = request.get_json()
        question = data.get('question', '').strip()
        
        if not question:
            return jsonify({"answer": "Por favor, escribe una pregunta válida."}), 400

        # 1. Generar SQL usando el ai_analyzer
        sql_query, error_ai = ai_analyzer.generate_sql_query(question)
        
        if error_ai:
            return jsonify({"answer": f"⚠️ Error de IA: {error_ai}"})

        # 2. Ejecutar SQL en la base de datos
        # Usamos una conexión fresca para cada consulta (mejor para Render)
        from db_manager import execute_dynamic_query
        columns, results, db_error = execute_dynamic_query(sql_query)

        if db_error:
            return jsonify({"answer": f"❌ Error de Base de Datos: {db_error}"})

        # 3. Interpretar resultados con IA
        final_response = ai_analyzer.generate_ai_response(
            question, columns, results, sql_query, db_error
        )

        return jsonify({"answer": final_response})

    except Exception as e:
        return jsonify({"answer": f"💥 Error crítico en el servidor: {str(e)}"}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)