from flask import Flask, request, jsonify, render_template
import os
import pandas as pd
from sqlalchemy import create_engine, text
from werkzeug.utils import secure_filename
from mistralai import Mistral
from datetime import datetime, timedelta

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'

# --- CONFIGURACIÓN DE MISTRAL ---
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "TU_CLAVE_AQUÍ")
client = Mistral(api_key=MISTRAL_API_KEY)
model_mistral = "mistral-large-latest"

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- BASE DE DATOS ---
def obtener_db_engine():
    DATABASE_URL = os.environ.get("DATABASE_URL")
    if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    # pool_pre_ping ayuda con los tiempos de espera largos de la IA
    return create_engine(DATABASE_URL, pool_pre_ping=True)

engine = obtener_db_engine()

# --- LÓGICA DE SUSCRIPCIÓN Y CRÉDITOS ---
def obtener_datos_usuario(usuario_id=1):
    """Consulta créditos y fechas en Supabase."""
    with engine.connect() as con:
        # Asegúrate de tener una tabla 'usuarios' con estas columnas
        query = text("SELECT creditos, fecha_inicio FROM usuarios WHERE id = :id")
        return con.execute(query, {"id": usuario_id}).fetchone()

def descontar_credito(usuario_id=1):
    """Actualiza el contador de créditos (Solución al 0/10)."""
    with engine.connect() as con:
        query = text("UPDATE usuarios SET creditos = creditos + 1 WHERE id = :id AND creditos < 10")
        con.execute(query, {"id": usuario_id})
        con.commit()

def calcular_banner():
    """Genera el banner según la fecha actual (30 de diciembre de 2025)."""
    hoy = datetime.now().date()
    vencimiento = datetime(2025, 12, 30).date()
    
    if hoy == vencimiento:
        return "Atención: Tu suscripción expira hoy. ¡Asegura tus datos!", "banner-warning"
    elif hoy == vencimiento + timedelta(days=1):
        return "Tu suscripción expiró ayer. Tienes un día de gracia disponible.", "banner-danger"
    return None, None

# --- RUTAS ---
@app.route('/')
def index():
    user = obtener_datos_usuario()
    mensaje_banner, clase_banner = calcular_banner()
    
    # Calculamos el día actual de la prueba (Imagen 6/7)
    dias_transcurridos = (datetime.now().date() - user.fecha_inicio).days
    dia_actual = max(0, min(7, dias_transcurridos)) 

    return render_template('index.html', 
                           creditos=user.creditos, 
                           dia_actual=dia_actual,
                           banner_msj=mensaje_banner,
                           banner_clase=clase_banner)

@app.route('/chat', methods=['POST'])
def chat():
    try:
        # 1. Verificar créditos antes de procesar
        user = obtener_datos_usuario()
        if user.creditos >= 10:
            return jsonify({"reply": "❌ Has agotado tus 10 créditos diarios de Visionary AI."})

        data = request.json
        user_message = data.get("message")
        
        # 2. Obtener contexto de ventas
        with engine.connect() as conn:
            df_contexto = pd.read_sql("SELECT producto, SUM(total) as ventas FROM ventas GROUP BY producto LIMIT 10", conn)
            resumen_datos = df_contexto.to_string(index=False)

        prompt_final = f"DATOS: {resumen_datos}\nPREGUNTA: {user_message}\nInstrucciones: Eres Visionary AI 🚀."

        # 3. Llamada a Mistral
        chat_response = client.chat.complete(
            model=model_mistral,
            messages=[{"role": "user", "content": prompt_final}]
        )
        
        # 4. ÉXITO: Descontar crédito en Supabase
        descontar_credito()
        
        return jsonify({"reply": chat_response.choices[0].message.content})

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"reply": "🚀 La IA está procesando datos pesados. ¡Reintenta en un momento!"})

# Mantenemos tu función de carga de Excel igual
@app.route('/upload', methods=['POST'])
def upload_file():
    # ... (Tu código de carga de archivo se mantiene igual) ...
    pass

if __name__ == '__main__':
    # Usar puerto 8000 para Koyeb
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)