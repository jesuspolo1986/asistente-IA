from flask import Flask, request, jsonify, render_template
import os
import pandas as pd
from sqlalchemy import create_engine, text
from werkzeug.utils import secure_filename
from mistralai import Mistral
from datetime import datetime, timedelta
import gc
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
# Límite de 16MB para seguridad del servidor
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 

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
    try:
        with engine.connect() as con:
            query = text("SELECT creditos_usados, fecha_inicio, plan FROM suscripciones WHERE id = 1")
            return con.execute(query).fetchone()
    except Exception as e:
        print(f"Error DB: {e}")
        return None

def registrar_uso_credito():
    """Incrementa el contador de créditos_usados."""
    try:
        with engine.connect() as con:
            with con.begin():
                query = text("UPDATE suscripciones SET creditos_usados = creditos_usados + 1 WHERE id = 1")
                con.execute(query)
    except Exception as e:
        print(f"Error al registrar crédito: {e}")

def gestionar_banner():
    """Lógica de gracia: Hoy vence (aviso) y mañana (gracia)."""
    hoy = datetime.now().date()
    vencimiento = datetime(2025, 12, 30).date() 
    
    if hoy == vencimiento:
        return "¡Tu suscripción vence hoy! Renueva para no perder acceso.", "banner-warning"
    elif hoy == vencimiento + timedelta(days=1):
        return "Tu suscripción venció ayer. Tienes un día de gracia disponible.", "banner-danger"
    return None, None

# --- RUTAS ---
@app.route('/')
def index():
    datos = obtener_datos_suscripcion()
    mensaje_banner, clase_banner = gestionar_banner()
    
    if datos:
        # Cálculo de días para la barra de progreso (simulado a 7 días)
        dias_transcurridos = (datetime.now().date() - datos.fecha_inicio).days
        dia_actual = max(0, min(7, dias_transcurridos))
        creditos = datos.creditos_usados
    else:
        dia_actual, creditos = 0, 0

    return render_template('index.html', 
                           creditos=creditos, 
                           dia_actual=dia_actual,
                           banner_msj=mensaje_banner,
                           banner_clase=clase_banner)

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        user_message = data.get("message")
        
        # 1. Extraer contexto (Asegúrate de que los nombres coincidan con ventas_prueba.csv)
        with engine.connect() as conn:
            # Usamos comillas dobles por si SQL se pone estricto con las mayúsculas de Pandas
            query = text('SELECT "Producto", SUM("Total") as ventas FROM ventas GROUP BY "Producto" LIMIT 10')
            df_contexto = pd.read_sql(query, conn)
            resumen_datos = df_contexto.to_string(index=False)

        prompt_final = f"DATOS REALES:\n{resumen_datos}\nPREGUNTA: {user_message}\nInstrucciones: Eres Visionary AI 🚀."

        # 2. Llamada a Mistral
        chat_response = client.chat.complete(
            model=model_mistral,
            messages=[{"role": "user", "content": prompt_final}]
        )
        
        registrar_uso_credito()
        return jsonify({"reply": chat_response.choices[0].message.content})

    except Exception as e:
        # ESTO APARECERÁ EN LOS LOGS DE KOYEB
        print(f"DEBUG ERROR CHAT: {type(e).__name__} - {str(e)}") 
        
        # Mensaje más informativo para ti mientras desarrollamos
        return jsonify({"reply": f"Error técnico: {type(e).__name__}. Revisa los logs de Koyeb."})
  # <--- Añade esto al principio del archivo con los otros imports

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"success": False, "message": "No hay archivo"}), 400
    
    file = request.files['file']
    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    try:
        file.save(file_path)

        # Leer archivo
        if filename.endswith('.csv'):
            df = pd.read_csv(file_path, encoding='utf-8-sig')
        else:
            df = pd.read_excel(file_path)

        # Subir a DB
        with engine.begin() as connection:
            df.to_sql('ventas', con=connection, if_exists='replace', index=False, chunksize=500)
        
        # --- LIBERACIÓN CRÍTICA DE MEMORIA ---
        del df               # Borra el objeto de datos
        if os.path.exists(file_path):
            os.remove(file_path) # Borra el archivo físico
        gc.collect()         # Fuerza a Python a limpiar la RAM
        # -------------------------------------

        return jsonify({"success": True, "message": "Datos cargados y memoria liberada."})

    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        return jsonify({"success": False, "message": str(e)}), 500
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)