import os
import pandas as pd
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import google.generativeai as genai
from sqlalchemy import text
from db_manager import engine, create_tables

app = Flask(__name__)
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
def upload_file():
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No hay archivo"})
    
    file = request.files['file']
    if file and file.filename.endswith('.csv'):
        try:
            # Lectura con detección de separador automático
            df = pd.read_csv(file, sep=None, engine='python', encoding='utf-8-sig')
            
            # Normalizar nombres de columnas (Fecha -> fecha, etc.)
            df.columns = [str(c).strip().lower().replace(' ', '_') for c in df.columns]
            
            # Subir a la tabla 'ventas'
            df.to_sql('ventas', con=engine, if_exists='append', index=False)
            return jsonify({"status": "success", "message": f"Se cargaron {len(df)} registros de ventas."})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)})
    return jsonify({"status": "error", "message": "Formato no compatible."})

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_question = data.get("message", "")
    model = genai.GenerativeModel('models/gemini-1.5-flash')

    try:
        with engine.connect() as conn:
            # Ahora Gemini analiza la tabla 'ventas'
            columns_info = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'ventas'")).fetchall()
            columnas = [row[0] for row in columns_info]

            # PROMPT DE SQL optimizado para ventas
            prompt = f"Eres un Analista SQL. Tabla: 'ventas'. Columnas: {', '.join(columnas)}. Pregunta: '{user_question}'. Genera solo el código SQL sin explicaciones."
            
            response = model.generate_content(prompt)
            sql_query = response.text.strip().replace('```sql', '').replace('```', '').strip()

            result = conn.execute(text(sql_query))
            data_result = result.fetchall()

            # RESPUESTA HUMANA
            interpretation_prompt = f"El usuario preguntó: '{user_question}'. Los datos de la base de datos son: {data_result}. Da una respuesta ejecutiva y breve."
            final_answer = model.generate_content(interpretation_prompt).text

            return jsonify({"reply": final_answer})

    except Exception as e:
        return jsonify({"reply": f"Error técnico: {str(e)}"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)