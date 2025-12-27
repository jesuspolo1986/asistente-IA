import os
import sqlite3
import pandas as pd
from flask import Flask, request, jsonify, render_template
from mistralai import Mistral

app = Flask(__name__)

# Configuración de Mistral
api_key = os.environ.get("MISTRAL_API_KEY")
model = "mistral-large-latest"
client = Mistral(api_key=api_key)

DATABASE = 'database.db'

def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto TEXT,
            monto REAL,
            fecha TEXT
        )
    ''')
    conn.commit()
    conn.close()
    print("Base de datos lista.")

init_db()

def obtener_contexto_db():
    try:
        conn = sqlite3.connect(DATABASE)
        # Obtener nombres de columnas
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(ventas)")
        columnas = [info[1] for info in cursor.fetchall()]
        
        # Obtener una muestra de los datos
        df = pd.read_sql_query("SELECT * FROM ventas LIMIT 5", conn)
        conn.close()
        
        if df.empty:
            return "La tabla está actualmente vacía. Esperando que el usuario suba datos."
        return f"Estructura de la tabla 'ventas': {columnas}. Ejemplo de datos: {df.to_dict(orient='records')}"
    except Exception as e:
        return f"Error leyendo base de datos: {e}"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({"error": "No hay archivo"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No seleccionado"}), 400

    try:
        # Cargar datos con Pandas y guardar en SQLite
        df = pd.read_csv(file) if file.filename.endswith('.csv') else pd.read_excel(file)
        conn = sqlite3.connect(DATABASE)
        df.to_sql('ventas', conn, if_exists='replace', index=False)
        conn.close()
        return jsonify({"reply": "✅ ¡Datos sincronizados! Ya puedes hacerme preguntas sobre este archivo."})
    except Exception as e:
        return jsonify({"error": f"Error al procesar: {str(e)}"}), 500

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_message = data.get("message")
    contexto = obtener_contexto_db()

    try:
        chat_response = client.chat.complete(
            model=model,
            messages=[
                {
                    "role": "system", 
                    "content": f"Eres AI Pro Analyst. USA ESTOS DATOS REALES: {contexto}. Responde de forma profesional usando tablas si es necesario."
                },
                {"role": "user", "content": user_message}
            ]
        )
        return jsonify({"reply": chat_response.choices[0].message.content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)