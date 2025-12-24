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
        # 1. Leer el archivo (usamos header=0 para buscar los títulos)
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            # Si el error persiste, podrías probar con skiprows=1 o 2 
            # si el archivo tiene muchas filas vacías al inicio
            df = pd.read_excel(BytesIO(file.read()))

        # 2. Limpieza de columnas "Unnamed" y basura
        df = df.loc[:, ~df.columns.str.contains('^Unnamed', case=False, na=False)]
        df.columns = [c.strip().replace(' ', '_').lower() for c in df.columns]
        
        # Eliminamos filas que estén totalmente vacías
        df = df.dropna(how='all')

        # 3. Carga Flexible a la DB
        db_url = os.environ.get("DATABASE_URL")
        engine = create_engine(db_url)
        
        # 'replace' borrará la tabla de ventas vieja y creará una 
        # con las columnas reales de tu Excel (Alumno, Nota, etc.)
        df.to_sql('datos_negocio', engine, if_exists='replace', index=False)

        return jsonify({
            "reply": f"✅ ¡Sincronización Exitosa! Se detectaron las columnas: {', '.join(df.columns)}. Se cargaron {len(df)} registros."
        })
    
    except Exception as e:
        return jsonify({"error": f"Error técnico: {str(e)}"}), 500
@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_question = data.get("message", "")
    # Aquí conectaremos la lógica de Gemini + SQL mañana
    return jsonify({"reply": f"Recibí tu consulta: '{user_question}'. Mañana activaremos el análisis con IA sobre los datos cargados."})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)