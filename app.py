from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import os
import pandas as pd
from sqlalchemy import create_engine, text
from werkzeug.utils import secure_filename
from mistralai import Mistral
from datetime import datetime

app = Flask(__name__)
app.secret_key = "analista_pro_final_2026"
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- CONFIGURACIÓN ---
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "TU_KEY")
client = Mistral(api_key=MISTRAL_API_KEY)
model_mistral = "mistral-large-latest"

# Conexión confirmada
DATABASE_URL = os.environ.get("DATABASE_URL", "").replace("postgres://", "postgresql://", 1)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

def gestionar_creditos(email):
    hoy = datetime.now().date()
    try:
        with engine.connect() as con:
            # Usamos public. para asegurar que encuentre la tabla
            res = con.execute(text('SELECT creditos_usados, ultimo_uso FROM public."suscripciones" WHERE email = :e'), {"e": email}).fetchone()
            
            if not res:
                with con.begin():
                    con.execute(text('INSERT INTO public."suscripciones" (email, creditos_usados, ultimo_uso) VALUES (:e, 0, :h)'), {"e": email, "h": hoy})
            
            if res.ultimo_uso != hoy:
                with con.begin():
                    con.execute(text('UPDATE public."suscripciones" SET creditos_usados = 0, ultimo_uso = :h WHERE email = :e'), {"e": email, "h": hoy})
                return 0
            return res.creditos_usados
    except Exception as e:
        print(f"Error Créditos: {e}")
        return 0

@app.route('/')
def index():
    if 'user' not in session: return render_template('index.html', login_mode=True)
    creditos = gestionar_creditos(session['user'])
    return render_template('index.html', login_mode=False, creditos=creditos, user=session['user'])

@app.route('/login', methods=['POST'])
def login():
    session['user'] = request.form.get('email').strip().lower()
    return redirect(url_for('index'))

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files['file']
    filename = secure_filename(file.filename)
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(path)
    try:
        df = pd.read_csv(path) if filename.endswith('.csv') else pd.read_excel(path)
        df.columns = [str(c).strip().lower() for c in df.columns]
        with engine.begin() as connection:
            # Forzamos la tabla ventas al esquema público
            df.to_sql('ventas', con=connection, if_exists='replace', index=False, schema='public')
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/chat', methods=['POST'])
def chat():
    user = session.get('user')
    creditos = gestionar_creditos(user)
    if creditos >= 10: return jsonify({"reply": "Límite diario alcanzado."})

    try:
        with engine.connect() as conn:
            df = pd.read_sql(text("SELECT * FROM public.ventas LIMIT 100"), conn)
        
        data = request.json
        prompt = f"Datos:\n{df.to_string()}\n\nPregunta: {data['message']}"
        resp = client.chat.complete(model=model_mistral, messages=[{"role": "user", "content": prompt}])
        
       # Cambia el UPDATE por este:
        with engine.begin() as con:
           con.execute(text('UPDATE public."suscripciones" SET creditos_usados = creditos_usados + 1 WHERE email = :e'), {"e": user})
            
        return jsonify({"reply": resp.choices[0].message.content})
    except Exception as e:
        return jsonify({"reply": f"Error: {str(e)}"})