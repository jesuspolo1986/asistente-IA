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
        return jsonify({"error": "No hay archivo"}), 400
    
    file = request.files['file']
    try:
        # 1. Leer desde la fila 11 (índice 10 en Python) 
        # donde están "APELLIDOS Y NOMBRES", "Promedio", etc.
        df = pd.read_excel(BytesIO(file.read()), skiprows=10)

        # 2. Limpieza de columnas vacías provocadas por celdas combinadas
        # Solo nos quedamos con las columnas que tienen nombres legibles
        df = df.loc[:, ~df.columns.str.contains('^Unnamed', case=False, na=False)]
        
        # 3. Eliminar filas vacías (como la fila 16 de tu imagen que está en blanco)
        df = df.dropna(subset=[df.columns[0]]) # Si no hay nombre, se elimina la fila

        # 4. Normalizar nombres de columnas
        df.columns = [str(c).strip().replace('\n', ' ').lower() for c in df.columns]

        # 5. Carga a la base de datos
        db_url = os.environ.get("DATABASE_URL")
        engine = create_engine(db_url)
        df.to_sql('planila_notas', engine, if_exists='replace', index=False)

        return jsonify({
            "reply": f"✅ ¡Sincronización Exitosa! Se detectó la planilla de: {df.columns[0].upper()}. Se cargaron {len(df)} alumnos correctamente."
        })
    
    except Exception as e:
        return jsonify({"error": f"Error en el formato: {str(e)}"}), 500
@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_question = data.get("message", "")
    # Aquí conectaremos la lógica de Gemini + SQL mañana
    return jsonify({"reply": f"Recibí tu consulta: '{user_question}'. Mañana activaremos el análisis con IA sobre los datos cargados."})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)