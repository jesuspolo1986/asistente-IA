import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import google.generativeai as genai
# Importamos las funciones de tu db_manager.py
from db_manager import create_tables, execute_dynamic_query

app = Flask(__name__)
CORS(app)

# 1. Configuración de Gemini
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("ERROR: Clave API no detectada en variables de entorno.")
else:
    genai.configure(api_key=GEMINI_API_KEY)
    print("✅ Conexión establecida con Gemini 2.0 Flash")

# 2. Inicialización de la Base de Datos
# Eliminamos el loop de asyncio y llamamos a la función directamente
try:
    print("INFO: Iniciando infraestructura en Koyeb...")
    create_tables()
    print("✅ Tablas creadas/verificadas en PostgreSQL")
except Exception as e:
    print(f"❌ Error al conectar/crear tablas: {e}")

@app.route('/')
def index():
    return "AI Pro Analyst is Running on Koyeb!"

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_message = data.get("message", "")
    
    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    try:
        # Aquí iría tu lógica para que Gemini analice la pregunta
        # y decida si ejecutar execute_dynamic_query
        response = "Sistema listo para procesar datos."
        return jsonify({"reply": response})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Koyeb usa el puerto 8000 por defecto
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)