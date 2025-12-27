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

import pandas as pd

@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files['file']
    if file and file.filename.endswith('.csv'):
        # Leemos el CSV
       # El parámetro sep=None con engine='python' detecta automáticamente si es coma o punto y coma
        df = pd.read_csv(file, sep=None, engine='python')
        
        # Lo subimos a la base de datos de Koyeb
        df.to_sql('ventas', con=engine, if_exists='append', index=False)
        
        return {"status": "success", "message": f"Se cargaron {len(df)} registros de ventas."}
    return {"status": "error", "message": "Formato no compatible."}
@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_question = data.get("message", "")
    
    db_url = os.environ.get("DATABASE_URL")
    engine = create_engine(db_url)

    try:
        with engine.connect() as conn:
            from sqlalchemy import text
            columns_info = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'planila_notas'")).fetchall()
            columnas = [row[0] for row in columns_info]

        # PROMPT DE SQL
        prompt = f"Eres un Analista SQL. Tabla: 'planila_notas'. Columnas: {', '.join(columnas)}. Pregunta: '{user_question}'. Genera solo el código SQL."

        # CAMBIO CLAVE AQUÍ:
        model = genai.GenerativeModel('models/gemini-flash-latest')
        
        response = model.generate_content(prompt)
        sql_query = response.text.strip().replace('```sql', '').replace('```', '').strip()

        with engine.connect() as conn:
            result = conn.execute(text(sql_query))
            data_result = result.fetchall()

        # RESPUESTA HUMANA
        interpretation_prompt = f"El usuario preguntó: '{user_question}'. Los datos obtenidos son: {data_result}. Responde de forma breve."
        final_answer = model.generate_content(interpretation_prompt).text

        return jsonify({"reply": final_answer})

    except Exception as e:
        return jsonify({"reply": f"Error técnico: {str(e)}"})
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)