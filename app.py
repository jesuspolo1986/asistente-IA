import os
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import google.generativeai as genai
from sqlalchemy import text
# Importamos las funciones exactas de db_manager
from db_manager import engine, create_tables, cargar_archivo_a_bd

app = Flask(__name__)
CORS(app)

# Configuración de Gemini
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Inicializar DB al arrancar (Aquí es donde se llamaba mal la función antes)
try:
    create_tables()
except Exception as e:
    print(f"Error inicializando tablas: {e}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No hay archivo"})
    
    file = request.files['file']
    if file and (file.filename.endswith('.csv') or file.filename.endswith('.xlsx')):
        # Guardar temporalmente en la carpeta /tmp de Koyeb
        temp_path = os.path.join("/tmp", file.filename)
        file.save(temp_path)
        
        success, message = cargar_archivo_a_bd(temp_path)
        
        if success:
            return jsonify({"status": "success", "message": message})
        else:
            return jsonify({"status": "error", "message": message})
    
    return jsonify({"status": "error", "message": "Formato no válido (use CSV o Excel)"})

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_question = data.get("message", "")
    model = genai.GenerativeModel('gemini-2.0-flash')

    try:
        with engine.connect() as conn:
            # Obtener columnas de la tabla 'ventas'
            columns_info = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'ventas'")).fetchall()
            columnas = [row[0] for row in columns_info]

            # Prompt para generar SQL
            prompt = f"Eres un Analista SQL experto. Tabla: 'ventas'. Columnas: {', '.join(columnas)}. Pregunta: '{user_question}'. Responde SOLO con el código SQL."
            
            response = model.generate_content(prompt)
            sql_query = response.text.strip().replace('```sql', '').replace('```', '').strip()

            # Ejecutar query
            result = conn.execute(text(sql_query))
            data_result = result.fetchall()

            # Respuesta humana
            interpretation_prompt = f"El usuario preguntó: '{user_question}'. Datos: {data_result}. Responde de forma breve y profesional."
            final_answer = model.generate_content(interpretation_prompt).text

            return jsonify({"reply": final_answer})

    except Exception as e:
        return jsonify({"reply": f"Error en consulta: {str(e)}"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)