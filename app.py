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
    try:
        # 1. Leer el archivo
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            # skiprows: Si tus datos reales empiezan más abajo, podrías probar con skiprows=5
            df = pd.read_excel(BytesIO(file.read()))

        # 2. Limpieza Crítica: Eliminar columnas "Unnamed"
        df = df.loc[:, ~df.columns.str.contains('^Unnamed', case=False, na=False)]
        
        # 3. Normalizar nombres
        df.columns = [c.lower().strip() for c in df.columns]

        # 4. Filtrar solo las columnas que existen en tu tabla de PostgreSQL
        # Esto evita el error de "UndefinedColumn"
        columnas_validas = ['producto', 'cantidad', 'precio']
        columnas_a_insertar = [c for c in df.columns if c in columnas_validas]
        
        if not columnas_a_insertar:
            return jsonify({"error": "El archivo no tiene las columnas requeridas (producto, cantidad, precio)"}), 400

        df_final = df[columnas_a_insertar]

        # 5. Carga a la DB
        db_url = os.environ.get("DATABASE_URL")
        engine = create_engine(db_url)
        df_final.to_sql('ventas', engine, if_exists='append', index=False)

        return jsonify({"reply": f"✅ ¡Éxito! Se sincronizaron {len(df_final)} registros. Se ignoraron columnas no compatibles."})
    
    except Exception as e:
        print(f"Error detalle: {str(e)}") # Esto saldrá en tus logs de Koyeb
        return jsonify({"error": f"Error al procesar: Verifica que el Excel tenga los títulos 'producto', 'cantidad' y 'precio'"}), 500
@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_question = data.get("message", "")
    # Aquí conectaremos la lógica de Gemini + SQL mañana
    return jsonify({"reply": f"Recibí tu consulta: '{user_question}'. Mañana activaremos el análisis con IA sobre los datos cargados."})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)