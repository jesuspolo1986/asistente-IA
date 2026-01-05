from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import os
import pandas as pd
from sqlalchemy import create_engine, text
from werkzeug.utils import secure_filename
from mistralai import Mistral
from datetime import datetime
import gc

app = Flask(__name__)
app.secret_key = "analista_pro_ultra_secret_2026"
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- CONFIGURACIÓN DE APIS ---
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "TU_KEY_AQUI")
client = Mistral(api_key=MISTRAL_API_KEY)
model_mistral = "mistral-large-latest"

# Conexión a Supabase (PostgreSQL) - Sin comillas en la lógica
engine = create_engine(
    os.environ.get("DATABASE_URL", "").replace("postgres://", "postgresql://", 1),
    pool_pre_ping=True
)

def gestionar_creditos(email):
    hoy = datetime.now().date()
    try:
        with engine.connect() as con:
            # Consulta limpia sin comillas para máxima compatibilidad
            query = text("SELECT creditos_usados, ultimo_uso FROM suscripciones WHERE email = :e")
            res = con.execute(query, {"e": email}).fetchone()
            
            if not res:
                # Si el usuario no existe, lo insertamos
                with con.begin():
                    con.execute(text("INSERT INTO suscripciones (email, creditos_usados, ultimo_uso) VALUES (:e, 0, :h)"), {"e": email, "h": hoy})
                return 0
            
            # Reset diario de créditos
            if res.ultimo_uso != hoy:
                with con.begin():
                    con.execute(text("UPDATE suscripciones SET creditos_usados = 0, ultimo_uso = :h WHERE email = :e"), {"e": email, "h": hoy})
                return 0
            
            return res.creditos_usados
    except Exception as e:
        print(f"DEBUG DB CREDITOS: {str(e)}")
        return 0

@app.route('/')
def index():
    if 'user' not in session:
        return render_template('index.html', login_mode=True)
    
    creditos = gestionar_creditos(session['user'])
    return render_template('index.html', login_mode=False, creditos=creditos, user=session['user'])

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
        df = pd.read_csv(path) if filename.endswith('.csv') else pd.read_excel(path)
        # Normalizamos nombres de columnas a minúsculas
        df.columns = [str(c).strip().lower() for c in df.columns]
        
        with engine.begin() as connection:
            # Reemplaza la tabla ventas con los nuevos datos
            df.to_sql('ventas', con=connection, if_exists='replace', index=False)
        
        if os.path.exists(path): os.remove(path)
        return jsonify({"success": True, "contexto": "Datos cargados exitosamente."})
    except Exception as e:
        print(f"DEBUG UPLOAD: {str(e)}")
        return jsonify({"success": False, "message": str(e)})

@app.route('/chat', methods=['POST'])
def chat():
    user = session.get('user')
    if not user: return jsonify({"reply": "Sesión expirada."})

    creditos = gestionar_creditos(user)
    if creditos >= 10:
        return jsonify({"reply": "🚫 Has alcanzado el límite de 10 consultas por hoy."})

    try:
        with engine.connect() as conn:
            # Lógica Universal: SELECT * de la tabla ventas
            df = pd.read_sql(text("SELECT * FROM ventas LIMIT 100"), conn)
        
        if df.empty:
            return jsonify({"reply": "⚠️ Sube un archivo antes de preguntar."})

        data = request.json
        prompt = f"Datos del Excel:\n{df.to_string()}\n\nPregunta: {data['message']}\nResponde de forma profesional."
        
        resp = client.chat.complete(model=model_mistral, messages=[{"role": "user", "content": prompt}])
        
        # COBRO DE CRÉDITO: Sin comillas para evitar el UndefinedTable
        with engine.begin() as con:
            con.execute(text("UPDATE suscripciones SET creditos_usados = creditos_usados + 1 WHERE email = :e"), {"e": user})
            
        return jsonify({"reply": resp.choices[0].message.content})
    except Exception as e:
        print(f"DEBUG CHAT ERROR: {str(e)}")
        return jsonify({"reply": f"❌ Error de conexión: {str(e)}"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)