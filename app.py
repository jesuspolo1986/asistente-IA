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
        # 1. Cargamos el Excel sin saltar filas inicialmente para analizarlo
        data = file.read()
        df_raw = pd.read_excel(BytesIO(data))

        # 2. BUSCADOR AUTOMÁTICO: Encontramos la fila donde están los nombres
        # Buscamos en todas las celdas la palabra "APELLIDOS"
        row_idx = None
        for i, row in df_raw.iterrows():
            if row.astype(str).str.contains('APELLIDOS', case=False, na=False).any():
                row_idx = i
                break
        
        if row_idx is not None:
            # Re-leer el archivo saltando exactamente hasta esa fila
            df = pd.read_excel(BytesIO(data), skiprows=row_idx + 1)
        else:
            # Si no lo encuentra, usamos un salto estándar de seguridad
            df = pd.read_excel(BytesIO(data), skiprows=10)

        # 3. Limpiar columnas vacías (Unnamed)
        df = df.loc[:, ~df.columns.str.contains('^Unnamed', case=False, na=False)]
        
        # 4. Limpiar nombres de columnas
        df.columns = [str(c).strip().replace('\n', ' ').lower() for c in df.columns]

        # 5. Filtrar filas: Solo nos interesan las que tienen un nombre de alumno
        # Usamos la primera columna (que debería ser nombres) para limpiar
        df = df.dropna(subset=[df.columns[0]])

        # 6. Carga a la base de datos
        db_url = os.environ.get("DATABASE_URL")
        engine = create_engine(db_url)
        df.to_sql('planila_notas', engine, if_exists='replace', index=False)

        return jsonify({
            "reply": f"✅ ¡Sincronización Lograda! Columnas: {', '.join(df.columns[:3])}... Se cargaron {len(df)} registros."
        })
    
    except Exception as e:
        return jsonify({"error": f"Error detectado: {str(e)}"}), 500
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