from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import os
import pandas as pd
from sqlalchemy import create_engine, text
from werkzeug.utils import secure_filename
from mistralai import Mistral
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "clave_secreta_visionary"
app.config['UPLOAD_FOLDER'] = 'uploads'

# --- CONFIGURACIÓN ---
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "TU_KEY")
client = Mistral(api_key=MISTRAL_API_KEY)
model_mistral = "mistral-large-latest"

engine = create_engine(os.environ.get("DATABASE_URL", "").replace("postgres://", "postgresql://", 1))

def gestionar_creditos(email):
    hoy = datetime.now().date()
    try:
        with engine.connect() as con:
            # Buscar usuario
            res = con.execute(text('SELECT creditos_usados, ultimo_uso FROM suscripciones WHERE email = :e'), {"e": email}).fetchone()
            
            if not res:
                with con.begin():
                    con.execute(text('INSERT INTO suscripciones (email, creditos_usados, ultimo_uso) VALUES (:e, 0, :h)'), {"e": email, "h": hoy})
                return 0
            
            # Reinicio diario
            if res.ultimo_uso != hoy:
                with con.begin():
                    con.execute(text('UPDATE suscripciones SET creditos_usados = 0, ultimo_uso = :h WHERE email = :e'), {"e": email, "h": hoy})
                return 0
            return res.creditos_usados
    except: return 0

@app.route('/')
def index():
    if 'user' not in session: return render_template('index.html', login_mode=True)
    
    creditos = gestionar_creditos(session['user'])
    vencimiento = datetime(2025, 12, 30).date()
    hoy = datetime.now().date()
    
    banner = None
    if hoy == vencimiento: banner = ("¡Tu suscripción vence hoy!", "banner-warning")
    elif hoy == vencimiento + timedelta(days=1): banner = ("Suscripción venció ayer (Día de Gracia)", "banner-danger")
    
    return render_template('index.html', login_mode=False, creditos=creditos, user=session['user'], banner=banner)

@app.route('/login', methods=['POST'])
def login():
    session['user'] = request.form.get('email')
    return redirect(url_for('index'))

@app.route('/chat', methods=['POST'])
def chat():
    user = session.get('user')
    creditos = gestionar_creditos(user)
    if creditos >= 10: return jsonify({"reply": "Límite diario alcanzado (10/10)."})

    data = request.json
    with engine.connect() as conn:
        df = pd.read_sql(text('SELECT * FROM ventas LIMIT 35'), conn)
    
    prompt = f"Datos: {df.to_string()}\nPregunta: {data['message']}"
    resp = client.chat.complete(model=model_mistral, messages=[{"role": "user", "content": prompt}])
    
    with engine.connect() as con:
        with con.begin():
            con.execute(text('UPDATE suscripciones SET creditos_usados = creditos_usados + 1 WHERE email = :e'), {"e": user})
            
    return jsonify({"reply": resp.choices[0].message.content})

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files['file']
    df = pd.read_csv(file) if file.filename.endswith('.csv') else pd.read_excel(file)
    # Detección de industria
    prompt = f"Columnas: {df.columns.tolist()}. ¿Qué industria es? (1 palabra)"
    res = client.chat.complete(model=model_mistral, messages=[{"role": "user", "content": prompt}])
    
    with engine.begin() as connection:
        df.to_sql('ventas', con=connection, if_exists='replace', index=False)
    return jsonify({"success": True, "contexto": res.choices[0].message.content.strip()})
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)