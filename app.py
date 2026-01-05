from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import os
import pandas as pd
from sqlalchemy import create_engine, text
from werkzeug.utils import secure_filename
from mistralai import Mistral
from datetime import datetime, timedelta
import gc

app = Flask(__name__)
app.secret_key = "visionary_pro_analyst_ultra_secret"
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- CONFIGURACIÓN ---
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "TU_KEY_AQUI")
client = Mistral(api_key=MISTRAL_API_KEY)
model_mistral = "mistral-large-latest"

# Conexión persistente a Supabase
engine = create_engine(
    os.environ.get("DATABASE_URL", "").replace("postgres://", "postgresql://", 1),
    pool_pre_ping=True,
    pool_recycle=3600
)

def gestionar_creditos(email):
    hoy = datetime.now().date()
    try:
        with engine.connect() as con:
            res = con.execute(text('SELECT creditos_usados, ultimo_uso FROM suscripciones WHERE email = :e'), {"e": email}).fetchone()
            
            if not res:
                with con.begin():
                    con.execute(text('INSERT INTO suscripciones (email, creditos_usados, ultimo_uso) VALUES (:e, 0, :h)'), {"e": email, "h": hoy})
                return 0
            
            if res.ultimo_uso != hoy:
                with con.begin():
                    con.execute(text('UPDATE suscripciones SET creditos_usados = 0, ultimo_uso = :h WHERE email = :e'), {"e": email, "h": hoy})
                return 0
            return res.creditos_usados
    except Exception as e:
        print(f"Log Créditos Error: {e}")
        return 0

@app.route('/')
def index():
    if 'user' not in session:
        return render_template('index.html', login_mode=True)
    
    creditos = gestionar_creditos(session['user'])
    vencimiento = datetime(2025, 12, 30).date()
    hoy = datetime.now().date()
    
    banner = None
    if hoy == vencimiento:
        banner = ("¡Tu suscripción vence hoy!", "banner-warning")
    elif hoy == vencimiento + timedelta(days=1):
        banner = ("Suscripción venció ayer (Día de Gracia)", "banner-danger")
    
    return render_template('index.html', login_mode=False, creditos=creditos, user=session['user'], banner=banner)

@app.route('/login', methods=['POST'])
def login():
    session['user'] = request.form.get('email').strip().lower()
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files: return jsonify({"success": False}), 400
    file = request.files['file']
    filename = secure_filename(file.filename)
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(path)
    
    try:
        # 1. Leer archivo
        df = pd.read_csv(path) if filename.endswith('.csv') else pd.read_excel(path)
        
        # 2. NORMALIZACIÓN UNIVERSAL: Todo a minúsculas y sin espacios
        df.columns = [str(c).strip().lower() for c in df.columns]
        
        # 3. Detectar industria antes de guardar
        prompt_ind = f"Columnas: {df.columns.tolist()}. ¿Industria? (1 palabra)"
        res_ia = client.chat.complete(model=model_mistral, messages=[{"role": "user", "content": prompt_ind}])
        contexto = res_ia.choices[0].message.content.strip()

        # 4. Guardar en SQL (reemplaza tabla 'ventas')
        with engine.begin() as connection:
            df.to_sql('ventas', con=connection, if_exists='replace', index=False)
        
        if os.path.exists(path): os.remove(path)
        gc.collect()
        return jsonify({"success": True, "contexto": contexto})
    except Exception as e:
        print(f"Error Upload: {e}")
        return jsonify({"success": False, "message": str(e)})

@app.route('/chat', methods=['POST'])
def chat():
    user = session.get('user')
    if not user: return jsonify({"reply": "Inicia sesión primero."})
    
    creditos = gestionar_creditos(user)
    if creditos >= 10:
        return jsonify({"reply": "🚫 Límite de 10 consultas diarias alcanzado."})

    try:
        with engine.connect() as conn:
            # Traer datos con nombres normalizados
            df = pd.read_sql(text('SELECT * FROM ventas LIMIT 50'), conn)
        
        if df.empty:
            return jsonify({"reply": "⚠️ La tabla está vacía. Sube el archivo de nuevo."})

        data = request.json
        prompt = f"DATOS DISPONIBLES:\n{df.to_string()}\n\nPREGUNTA: {data['message']}\nEres Visionary AI. Analiza con precisión."
        
        resp = client.chat.complete(model=model_mistral, messages=[{"role": "user", "content": prompt}])
        
        # Solo descontamos crédito si la IA respondió bien
        with engine.begin() as con:
            con.execute(text('UPDATE suscripciones SET creditos_usados = creditos_usados + 1 WHERE email = :e'), {"e": user})
            
        return jsonify({"reply": resp.choices[0].message.content})
    except Exception as e:
        print(f"Error Chat: {e}")
        return jsonify({"reply": "Sube un archivo primero (la tabla 'ventas' no está lista)."})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)