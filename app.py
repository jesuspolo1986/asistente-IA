from flask import Flask, request, jsonify, render_template
import os
import pandas as pd
from sqlalchemy import create_engine, text
from werkzeug.utils import secure_filename
from mistralai import Mistral
from datetime import datetime, timedelta

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'

# --- CONFIGURACIÓN DE APIS Y DB ---
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "TU_CLAVE_AQUÍ")
client = Mistral(api_key=MISTRAL_API_KEY)
model_mistral = "mistral-large-latest"

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def obtener_db_engine():
    """Configura el motor compatible con Koyeb y Supabase."""
    DATABASE_URL = os.environ.get("DATABASE_URL", "")
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    return create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)

engine = obtener_db_engine()

# --- LÓGICA DE SUSCRIPCIÓN Y CRÉDITOS ---
def obtener_datos_suscripcion():
    """Consulta la tabla suscripciones (ID 1) en Supabase."""
    with engine.connect() as con:
        query = text("SELECT creditos_usados, fecha_inicio, plan FROM suscripciones WHERE id = 1")
        return con.execute(query).fetchone()

def registrar_uso_credito():
    """Incrementa el contador de créditos_usados en Supabase."""
    with engine.connect() as con:
        with con.begin():
            query = text("UPDATE suscripciones SET creditos_usados = creditos_usados + 1 WHERE id = 1")
            con.execute(query)

def gestionar_banner():
    """Lógica de gracia: Hoy 30 de dic y mañana 31 de dic."""
    hoy = datetime.now().date()
    # Fecha de vencimiento establecida por el usuario
    vencimiento = datetime(2025, 12, 30).date()
    
    if hoy == vencimiento:
        return "Atención: Tu suscripción expira hoy. ¡Asegura tus datos!", "banner-warning"
    elif hoy == vencimiento + timedelta(days=1):
        return "Tu suscripción expiró ayer. Tienes un día de gracia disponible.", "banner-danger"
    return None, None

# --- RUTAS ---
@app.route('/')
def index():
    try:
        datos = obtener_datos_suscripcion()
        mensaje_banner, clase_banner = gestionar_banner()
        
        # Cálculo de días para la barra de progreso (Imagen 6/7)
        dias_transcurridos = (datetime.now().date() - datos.fecha_inicio).days
        dia_actual = max(0, min(7, dias_transcurridos))

        return render_template('index.html', 
                               creditos=datos.creditos_usados, 
                               dia_actual=dia_actual,
                               banner_msj=mensaje_banner,
                               banner_clase=clase_banner)
    except Exception as e:
        return f"Error al cargar base de datos: {str(e)}"

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        user_message = data.get("message")
        
        # 1. Intentar registrar crédito (0/10)
        try:
            registrar_uso_credito()
        except:
            pass # Si falla la DB, permitimos el chat para no bloquear al usuario

        # 2. Extraer contexto de ventas
        with engine.connect() as conn:
            df_contexto = pd.read_sql("SELECT producto, SUM(total) as ventas FROM ventas GROUP BY producto LIMIT 10", conn)
            resumen_datos = df_contexto.to_string(index=False)

        prompt_final = f"DATOS REALES:\n{resumen_datos}\nPREGUNTA: {user_message}\nInstrucciones: Eres Visionary AI 🚀."

        # 3. Llamada a Mistral
        chat_response = client.chat.complete(
            model=model_mistral,
            messages=[{"role": "user", "content": prompt_final}]
        )
        
        return jsonify({"reply": chat_response.choices[0].message.content})
    except Exception as e:
        return jsonify({"reply": "🚀 La IA está procesando datos. ¡Intenta de nuevo!"})

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"success": False, "message": "No hay archivo"}), 400
    
    file = request.files['file']
    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(file_path)

    try:
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path, encoding='utf-8-sig')
        else:
            df = pd.read_excel(file_path)
        
        with engine.begin() as connection:
            df.to_sql('ventas', con=connection, if_exists='replace', index=False)
        
        return jsonify({"success": True, "message": f"Éxito: {len(df)} registros analizados."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)
