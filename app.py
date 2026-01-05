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
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 

# --- CONFIGURACIÓN ---
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "TU_CLAVE_AQUÍ")
client = Mistral(api_key=MISTRAL_API_KEY)
model_mistral = "mistral-large-latest"

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def obtener_db_engine():
    DATABASE_URL = os.environ.get("DATABASE_URL", "")
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    return create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)

engine = obtener_db_engine()

# --- LÓGICA DE SUSCRIPCIÓN ---
def obtener_datos_suscripcion():
    try:
        with engine.connect() as con:
            query = text("SELECT creditos_usados, fecha_inicio, plan FROM suscripciones WHERE id = 1")
            return con.execute(query).fetchone()
    except:
        return None

def registrar_uso_credito():
    try:
        with engine.connect() as con:
            with con.begin():
                con.execute(text("UPDATE suscripciones SET creditos_usados = creditos_usados + 1 WHERE id = 1"))
    except:
        pass

# --- RUTAS ---
@app.route('/')
def index():
    datos = obtener_datos_suscripcion()
    # Fecha de vencimiento configurada según tus instrucciones (30 Dic + 1 día gracia)
    vencimiento = datetime(2025, 12, 30).date()
    hoy = datetime.now().date()
    
    mensaje_banner, clase_banner = None, None
    if hoy == vencimiento:
        mensaje_banner, clase_banner = "¡Tu suscripción vence hoy!", "banner-warning"
    elif hoy == vencimiento + timedelta(days=1):
        mensaje_banner, clase_banner = "Tu suscripción venció ayer (Día de Gracia).", "banner-danger"

    creditos = datos.creditos_usados if datos else 0
    return render_template('index.html', creditos=creditos, banner_msj=mensaje_banner, banner_clase=clase_banner)

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        user_message = data.get("message")
        
        # ESTRATEGIA UNIVERSAL:
        # Leemos las primeras 40 filas de la tabla sin importar cómo se llamen las columnas
        with engine.connect() as conn:
            df_contexto = pd.read_sql(text('SELECT * FROM ventas LIMIT 40'), conn)
            columnas = df_contexto.columns.tolist()
            resumen_datos = df_contexto.to_string(index=False)

        prompt_final = (
            f"Eres Visionary AI 🚀. Analiza estos datos empresariales:\n"
            f"COLUMNAS DETECTADAS: {columnas}\n"
            f"DATOS:\n{resumen_datos}\n\n"
            f"PREGUNTA: {user_message}\n"
            f"INSTRUCCIÓN: Responde basado en los datos. Si necesitas sumar valores, hazlo."
        )

        chat_response = client.chat.complete(
            model=model_mistral,
            messages=[{"role": "user", "content": prompt_final}]
        )
        
        registrar_uso_credito()
        return jsonify({"reply": chat_response.choices[0].message.content})

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"reply": "🚀 La IA está procesando los nuevos encabezados. ¡Reintenta!"})

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"success": False, "message": "No hay archivo"}), 400
    
    file = request.files['file']
    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    try:
        file.save(file_path)
        # Soporte para CSV y Excel
        df = pd.read_csv(file_path) if filename.endswith('.csv') else pd.read_excel(file_path)

        # INSERTAR EN DB (Universal: reemplaza la tabla con la estructura del nuevo archivo)
        with engine.begin() as connection:
            df.to_sql('ventas', con=connection, if_exists='replace', index=False, chunksize=500)
        
        # LIBERACIÓN DE MEMORIA
        del df
        if os.path.exists(file_path): os.remove(file_path)
        gc.collect()

        return jsonify({"success": True, "message": "Archivo procesado con éxito."})

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)