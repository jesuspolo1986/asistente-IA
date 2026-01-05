from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import os
import pandas as pd
from sqlalchemy import create_engine, text
from werkzeug.utils import secure_filename
from mistralai import Mistral
from datetime import datetime, timedelta
import gc

app = Flask(__name__)
app.secret_key = "visionary_ai_secret_key_2026" # Clave para las sesiones
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- CONFIGURACIÓN DE APIS ---
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "TU_KEY_AQUI")
client = Mistral(api_key=MISTRAL_API_KEY)
model_mistral = "mistral-large-latest"

# Conexión a Supabase (PostgreSQL)
engine = create_engine(
    os.environ.get("DATABASE_URL", "").replace("postgres://", "postgresql://", 1),
    pool_pre_ping=True
)

# --- LÓGICA DE CRÉDITOS ---
def gestionar_creditos(email):
    hoy = datetime.now().date()
    try:
        with engine.connect() as con:
            # Buscamos al usuario por su email
            query = text('SELECT creditos_usados, ultimo_uso FROM "suscripciones" WHERE email = :e')
            res = con.execute(query, {"e": email}).fetchone()
            
            if not res:
                # Si el usuario no existe en la tabla, lo creamos
                with con.begin():
                    con.execute(text('INSERT INTO "suscripciones" (email, creditos_usados, ultimo_uso) VALUES (:e, 0, :h)'), {"e": email, "h": hoy})
                return 0
            
            # Si es un nuevo día, reseteamos sus créditos a 0
            if res.ultimo_uso != hoy:
                with con.begin():
                    con.execute(text('UPDATE "suscripciones" SET creditos_usados = 0, ultimo_uso = :h WHERE email = :e'), {"e": email, "h": hoy})
                return 0
            
            return res.creditos_usados
    except Exception as e:
        print(f"Error en DB (Créditos): {e}")
        return 0

# --- RUTAS ---

@app.route('/')
def index():
    if 'user' not in session:
        return render_template('index.html', login_mode=True)
    
    email_usuario = session['user']
    creditos = gestionar_creditos(email_usuario)
    
    # Lógica de suscripción (según tus fechas de 2025/2026)
    vencimiento = datetime(2025, 12, 30).date()
    hoy = datetime.now().date()
    
    banner = None
    if hoy == vencimiento:
        banner = ("¡Tu suscripción vence hoy!", "banner-warning")
    elif hoy == vencimiento + timedelta(days=1):
        banner = ("Suscripción venció ayer (Día de Gracia)", "banner-danger")
    
    return render_template('index.html', 
                           login_mode=False, 
                           creditos=creditos, 
                           user=email_usuario, 
                           banner=banner)

@app.route('/login', methods=['POST'])
def login():
    session['user'] = request.form.get('email')
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))

@app.route('/chat', methods=['POST'])
def chat():
    user = session.get('user')
    if not user: return jsonify({"reply": "Por favor, inicia sesión."})

    creditos = gestionar_creditos(user)
    if creditos >= 10:
        return jsonify({"reply": "🚫 Límite diario de 10 consultas alcanzado. ¡Vuelve mañana! 🚀"})

    data = request.json
    try:
        with engine.connect() as conn:
            # LÓGICA UNIVERSAL: Traemos todo de la tabla 'ventas'
            df = pd.read_sql(text('SELECT * FROM ventas LIMIT 40'), conn)
        
        if df.empty:
            return jsonify({"reply": "La tabla de datos está vacía. Por favor, sube un archivo válido."})

        # Enviamos los datos a la IA para que ella interprete las columnas
        prompt = f"Analiza estos datos:\n{df.to_string()}\n\nPregunta del usuario: {data['message']}\nResponde como Visionary AI 🚀."
        resp = client.chat.complete(model=model_mistral, messages=[{"role": "user", "content": prompt}])
        
        # Si la respuesta fue exitosa, descontamos crédito
        with engine.connect() as con:
            with con.begin():
                con.execute(text('UPDATE "suscripciones" SET creditos_usados = creditos_usados + 1 WHERE email = :e'), {"e": user})
                
        return jsonify({"reply": resp.choices[0].message.content})
    except Exception as e:
        print(f"Error en Chat: {e}")
        return jsonify({"reply": "Error: Asegúrate de haber subido un archivo CSV o Excel primero."})

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files: return jsonify({"success": False, "message": "No hay archivo"}), 400
    
    file = request.files['file']
    filename = secure_filename(file.filename)
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(path)
    
    try:
        # Carga dinámica
        df = pd.read_csv(path) if filename.endswith('.csv') else pd.read_excel(path)
        
        # Identificar industria con IA
        prompt_ind = f"Columnas: {df.columns.tolist()}. ¿Qué industria es? Responde en una palabra."
        res_ia = client.chat.complete(model=model_mistral, messages=[{"role": "user", "content": prompt_ind}])
        contexto = res_ia.choices[0].message.content.strip()
        
        # Guardar en base de datos reemplazando la anterior
        with engine.begin() as connection:
            df.to_sql('ventas', con=connection, if_exists='replace', index=False)
        
        # Limpieza de archivos temporales y memoria
        if os.path.exists(path): os.remove(path)
        gc.collect()
        
        return jsonify({"success": True, "contexto": contexto})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)