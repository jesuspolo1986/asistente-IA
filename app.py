import os
import pandas as pd
from io import BytesIO
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import google.generativeai as genai
from sqlalchemy import create_engine
from db_manager import create_tables

# Configuración de rutas para Koyeb
base_dir = os.path.abspath(os.path.dirname(__file__))
template_dir = os.path.join(base_dir, 'templates')

app = Flask(__name__, template_folder=template_dir)
CORS(app)

# Configuración de Gemini
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Inicializar DB al arrancar
try:
    create_tables()
except Exception as e:
    print(f"Error inicializando tablas: {e}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({"error": "No se seleccionó ningún archivo"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Nombre de archivo vacío"}), 400

    try:
        # Leer archivo según extensión
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            # openpyxl es necesario para .xlsx
            df = pd.read_excel(BytesIO(file.read()))

        # Normalizar nombres de columnas a minúsculas
        df.columns = [c.lower().strip() for c in df.columns]

        # Conexión y carga a PostgreSQL
        db_url = os.environ.get("DATABASE_URL")
        if not db_url:
            return jsonify({"error": "DATABASE_URL no configurada"}), 500
            
        engine = create_engine(db_url)
        # Cargamos los datos en la tabla 'ventas'
        df.to_sql('ventas', engine, if_exists='append', index=False)

        return jsonify({"reply": f"✅ ¡Éxito! Se cargaron {len(df)} filas desde '{file.filename}' a la base de datos."})
    
    except Exception as e:
        return jsonify({"error": f"Error al procesar el archivo: {str(e)}"}), 500

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_question = data.get("message", "")
    # Aquí conectaremos la lógica de Gemini + SQL mañana
    return jsonify({"reply": f"Recibí tu consulta: '{user_question}'. Mañana activaremos el análisis con IA sobre los datos cargados."})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)