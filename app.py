import os
import sqlite3
from flask import Flask, request, jsonify, render_template
from mistralai import Mistral

app = Flask(__name__)

# Configuración de Mistral - Asegúrate de poner MISTRAL_API_KEY en Koyeb
api_key = os.environ.get("MISTRAL_API_KEY")
model = "mistral-large-latest"
client = Mistral(api_key=api_key)

# Inicializar Base de Datos (Mantiene tu tabla 'ventas')
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto TEXT,
            monto REAL,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    print("Base de datos lista: Tabla 'ventas' creada.")

init_db()

@app.route('/')
def index():
    return render_template('index.html') # O el nombre de tu archivo HTML

@app.route('/upload', methods=['POST'])
def upload():
    # Aquí va tu lógica de subida de archivos/datos
    return jsonify({"reply": "success", "message": "Datos recibidos"})

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_message = data.get("message")

    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    try:
        # Llamada a la API de Mistral
        chat_response = client.chat.complete(
            model=model,
            messages=[
                {"role": "user", "content": user_message}
            ]
        )
        
        respuesta_texto = chat_response.choices[0].message.content
        return jsonify({"reply": respuesta_texto})

    except Exception as e:
        print(f"Error con Mistral: {e}")
        return jsonify({"error": "Error al procesar la solicitud"}), 500
@app.route('/favicon.ico')
def favicon():
    return '', 204

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)