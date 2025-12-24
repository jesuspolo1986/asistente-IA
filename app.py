import os
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import google.generativeai as genai
from db_manager import create_tables
template_dir = os.path.abspath('templates')
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
    # Renderiza tu HTML profesional
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    # Aquí capturamos la pregunta del textarea de tu HTML
    user_question = data.get("message") 
    
    # Por ahora devolvemos una respuesta de prueba
    # Mañana conectaremos esto con la lógica de SQL y Gráficos
    return jsonify({
        "reply": f"<h3>Análisis Recibido</h3><p>Pronto procesaré: <b>{user_question}</b></p>"
    })

@app.route('/upload', methods=['POST'])
def upload():
    # Este es el espacio para la función de Excel que haremos mañana
    return jsonify({"message": "Sincronización exitosa (Simulada)"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)