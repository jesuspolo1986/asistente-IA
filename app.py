from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import os
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from mistralai import Mistral

app = Flask(__name__)
app.secret_key = "analista_pro_final_2026"
app.config['UPLOAD_FOLDER'] = 'uploads'

# --- CONFIGURACIÓN DE DB Y MISTRAL ---
DATABASE_URL = os.environ.get("DATABASE_URL", "").replace("postgres://", "postgresql://", 1)
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")

engine = create_engine(DATABASE_URL, pool_size=5, max_overflow=10, pool_pre_ping=True)
client = Mistral(api_key=MISTRAL_API_KEY)

# Asegurar que la carpeta de subidas existe
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

@app.route('/')
def index():
    if 'user' not in session: return render_template('index.html', login_mode=True)
    
    email = session['user']
    hoy = datetime.now().date()
    
    with engine.connect() as conn:
        res = conn.execute(text("SELECT fecha_vencimiento, creditos_usados FROM suscripciones WHERE email = :e"), {"e": email}).fetchone()
    
    if not res: return redirect(url_for('logout'))
    
    vence, usados = res[0], res[1] or 0
    banner = None
    
    # Lógica de Gracia y Vencimiento [cite: 2025-12-30]
    if hoy <= vence: 
        estado = "Activo"
    elif hoy == vence + timedelta(days=1): 
        estado = "Gracia"
        banner = ("⚠️ Día de Gracia: Tu suscripción venció ayer.", "alert-warning")
    else: 
        estado = "Vencido"
        banner = ("🚫 Suscripción Vencida. Acceso limitado.", "alert-danger")
        
    return render_template('index.html', login_mode=False, user=email, estado=estado, creditos=usados, banner=banner)

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email').strip().lower()
    session['user'] = email
    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO suscripciones (email, fecha_vencimiento) 
            VALUES (:e, CURRENT_DATE + INTERVAL '30 days') 
            ON CONFLICT (email) DO NOTHING
        """), {"e": email})
        conn.commit()
    return redirect(url_for('index'))

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({"error": "No hay archivo"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Sin nombre"}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    session['last_file'] = filename
    return jsonify({"success": True, "message": f"Archivo {filename} listo para análisis."})

@app.route('/chat', methods=['POST'])
def chat():
    user_msg = request.json.get('message')
    filename = session.get('last_file')
    
    if not filename:
        return jsonify({"response": "Por favor, sube un archivo primero."})

    try:
        # Leer datos para dar contexto a la IA [cite: 2025-12-19]
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        df = pd.read_csv(filepath) if filename.endswith('.csv') else pd.read_excel(filepath)
        contexto = df.head(10).to_string()

        prompt = f"Datos del archivo:\n{contexto}\n\nPregunta del usuario: {user_msg}"
        
        chat_response = client.chat.complete(
            model="mistral-tiny",
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Consumir crédito
        with engine.connect() as conn:
            conn.execute(text("UPDATE suscripciones SET creditos_usados = creditos_usados + 1 WHERE email = :e"), {"e": session['user']})
            conn.commit()

        return jsonify({"response": chat_response.choices[0].message.content})
    except Exception as e:
        return jsonify({"response": f"Error analizando datos: {str(e)}"})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))