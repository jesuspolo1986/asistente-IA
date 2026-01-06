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
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "TU_MISTRAL_KEY")
client = Mistral(api_key=MISTRAL_API_KEY)

# Conexión reconstruida con tu ID de proyecto
DATABASE_URL = os.environ.get("DATABASE_URL", "").replace("postgres://", "postgresql://", 1)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

def inicializar_db():
    """Crea la tabla si no existe al arrancar la app"""
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS public.suscripciones (
                email TEXT PRIMARY KEY,
                creditos_usados INTEGER DEFAULT 0,
                ultimo_uso DATE DEFAULT CURRENT_DATE
            );
        """))

def gestionar_creditos(email):
    hoy = datetime.now().date()
    try:
        with engine.connect() as con:
            res = con.execute(text('SELECT creditos_usados, ultimo_uso FROM public.suscripciones WHERE email = :e'), {"e": email}).fetchone()
            if not res:
                with con.begin():
                    con.execute(text('INSERT INTO public.suscripciones (email, creditos_usados, ultimo_uso) VALUES (:e, 0, :h)'), {"e": email, "h": hoy})
                return 0
            if res.ultimo_uso != hoy:
                with con.begin():
                    con.execute(text('UPDATE public.suscripciones SET creditos_usados = 0, ultimo_uso = :h WHERE email = :e'), {"e": email, "h": hoy})
                return 0
            return res.creditos_usados
    except Exception as e:
        print(f"Error DB: {e}")
        return 0

@app.route('/')
def index():
    if 'user' not in session: return render_template('index.html', login_mode=True)
    creditos = gestionar_creditos(session['user'])
    # Mañana integraremos aquí el banner de expiración y el día de gracia [cite: 2025-12-30]
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
            df.to_sql('ventas', con=connection, if_exists='replace', index=False, schema='public')
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/chat', methods=['POST'])
def chat():
    user = session.get('user')
    creditos = gestionar_creditos(user)
    if creditos >= 10: return jsonify({"reply": "Límite alcanzado."})

    try:
        with engine.connect() as conn:
            df = pd.read_sql(text("SELECT * FROM public.ventas LIMIT 100"), conn)
        
        data = request.json
        # NUEVA ESTRUCTURA DE PROMPT PARA MAYOR INTELIGENCIA
        prompt = f"""
        Actúa como un Analista de Negocios Senior (AI Pro Analyst). 
        Contexto del negocio (Primeras 100 filas):
        {df.to_string()}

        Instrucciones:
        1. No te limites a sumar. Busca patrones, tendencias y anomalías.
        2. Si el usuario pregunta por ventas totales, da el número pero también menciona quién es el mejor vendedor o qué producto destaca.
        3. Usa un tono ejecutivo y profesional.
        4. Si detectas algo preocupante (ej. un vendedor con muy pocas ventas), menciónalo como una 'Oportunidad de Mejora'.

        Pregunta del usuario: {data['message']}
        """
        
        resp = client.chat.complete(model="mistral-large-latest", messages=[{"role": "user", "content": prompt}])
        
        with engine.begin() as con:
            con.execute(text('UPDATE public.suscripciones SET creditos_usados = creditos_usados + 1 WHERE email = :e'), {"e": user})
            
        return jsonify({"reply": resp.choices[0].message.content})
    except Exception as e:
        return jsonify({"reply": f"Error en el análisis: {str(e)}"})
if __name__ == '__main__':
    # Aseguramos que las tablas existan antes de atender usuarios
    try:
        inicializar_db()
    except:
        pass
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))