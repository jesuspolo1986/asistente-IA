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
    # Aseguramos que la tabla exista con una estructura inicial
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
    print("Base de datos inicializada.")

init_db()

def obtener_contexto_db():
    try:
        conn = sqlite3.connect(DATABASE)
        # PRAGMA ayuda a obtener la estructura real actual
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(ventas)")
        columnas = [info[1] for info in cursor.fetchall()]
        
        # Leemos una muestra de los datos guardados
        df = pd.read_sql_query("SELECT * FROM ventas LIMIT 5", conn)
        conn.close()
        
        if df.empty:
            return "La tabla está vacía. El usuario aún no ha cargado datos válidos."
        
        return f"Estructura actual: {columnas}. Muestra de datos: {df.to_dict(orient='records')}"
    except Exception as e:
        return f"Error leyendo base de datos: {e}"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({"error": "No se encontró el archivo en la petición"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No has seleccionado ningún archivo"}), 400

    try:
        # LECTURA ROBUSTA: 
        # sep=None y engine='python' detectan automáticamente si es coma (,) o punto y coma (;)
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file, sep=None, engine='python', on_bad_lines='warn')
        else:
            df = pd.read_excel(file)

        # Limpiar nombres de columnas (quitar espacios raros)
        df.columns = [c.strip() for c in df.columns]

        conn = sqlite3.connect(DATABASE)
        # 'replace' sobreescribe la tabla con la nueva estructura del archivo subido
        df.to_sql('ventas', conn, if_exists='replace', index=False)
        conn.close()
        
        return jsonify({"reply": f"✅ ¡Éxito! Se cargaron {len(df)} filas. Columnas detectadas: {list(df.columns)}. ¿Qué deseas analizar?"})
    
    except Exception as e:
        print(f"Error detallado en upload: {str(e)}")
        return jsonify({"error": f"Error al procesar el archivo: {str(e)}"}), 500

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_message = data.get("message")
    
    # Obtenemos lo que realmente hay en la DB ahora mismo
    contexto = obtener_contexto_db()

    try:
        chat_response = client.chat.complete(
            model=model,
            messages=[
                {
                    "role": "system", 
                    "content": (
                        "Eres AI Pro Analyst, un experto en análisis de datos. "
                        f"CONTEXTO REAL DE LA BASE DE DATOS: {contexto}. "
                        "Responde de forma concisa. Si el usuario pregunta por columnas o datos, "
                        "usa EXCLUSIVAMENTE la información del contexto arriba facilitado. "
                        "Si la tabla está vacía, pide al usuario que suba un archivo primero."
                    )
                },
                {"role": "user", "content": user_message}
            ]
        )
        return jsonify({"reply": chat_response.choices[0].message.content})
    except Exception as e:
        print(f"Error en Chat: {e}")
        return jsonify({"error": "Hubo un problema con la IA."}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)