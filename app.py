import os
import pandas as pd
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from mistralai import Mistral

app = Flask(__name__)
app.secret_key = "analista_pro_v5_estabilidad_total"
app.config['UPLOAD_FOLDER'] = 'uploads'

# --- CONFIGURACIÓN DE ENTORNO ---
# Nota: La URL directa (puerto 5432) es la que mejor te funcionará en local
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:YNjscilzeWI9LbzR@db.kebpamfydhnxeaeegulx.supabase.co:5432/postgres").replace("postgres://", "postgresql://", 1)
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")

engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20)
client = Mistral(api_key=MISTRAL_API_KEY)

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# --- LOGS DE SEGURIDAD (Mantiene trazabilidad sin panel pesado) ---
def registrar_log(email, accion, detalle):
    try:
        with engine.connect() as conn:
            conn.execute(text("INSERT INTO logs_actividad (email, accion, detalle) VALUES (:e, :a, :d)"),
                         {"e": email, "a": accion, "d": detalle})
            conn.commit()
    except Exception as e:
        print(f"Error log: {e}")

# --- RUTAS PRINCIPALES ---
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
    
    # Lógica de suscripción y periodo de gracia
    if hoy <= vence: 
        estado = "Activo"
    elif hoy == vence + timedelta(days=1): 
        estado = "Gracia"
        banner = ("⚠️ Tu suscripción venció ayer. Hoy es tu último día de gracia.", "alert-warning")
    else: 
        estado = "Vencido"
        banner = ("🚫 Suscripción expirada. Acceso restringido.", "alert-danger")
    
    return render_template('index.html', login_mode=False, user=email, estado=estado, creditos=usados, banner=banner)

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email').strip().lower()
    session['user'] = email
    with engine.connect() as conn:
        conn.execute(text("INSERT INTO suscripciones (email, fecha_vencimiento) VALUES (:e, CURRENT_DATE + INTERVAL '30 days') ON CONFLICT (email) DO NOTHING"), {"e": email})
        conn.commit()
    registrar_log(email, "LOGIN", "Ingreso al sistema")
    return redirect(url_for('index'))

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files.get('file')
    if not file: return jsonify({"error": "No file"}), 400
    email = session.get('user', 'unknown')
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    session['last_file'] = filename
    registrar_log(email, "UPLOAD", f"Archivo: {filename}")
    return jsonify({"success": True})

@app.route('/chat', methods=['POST'])
def chat():
    user_msg = request.json.get('message', '').lower()
    email = session.get('user', 'unknown')
    filename = session.get('last_file')
    if not filename: return jsonify({"response": "Sube un archivo primero."})

    try:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        df = pd.read_csv(filepath) if filename.endswith('.csv') else pd.read_excel(filepath)
        
        cols = df.columns.tolist()
        col_sujeto = next((c for c in cols if c.lower() in ['vendedor', 'conductor', 'tienda', 'sku', 'empleado']), cols[0])
        col_valor = next((c for c in cols if c.lower() in ['total', 'ventas', 'monto', 'cantidad']), cols[-1])
        
        ranking = df.groupby(col_sujeto)[col_valor].sum().sort_values(ascending=False)
        
        # Interceptor de lógica rápida
        if any(w in user_msg for w in ["mejor", "ganador", "lider", "mas vendio"]):
            return jsonify({"response": f"📊 El líder es **{ranking.index[0]}** con {ranking.iloc[0]:,.2f}."})

        # IA Analysis
        response = client.chat.complete(
            model="mistral-small",
            messages=[
                {"role": "system", "content": f"Analista experto. Datos: {df.head(5).to_dict()}. Líder: {ranking.index[0]}"},
                {"role": "user", "content": user_msg}
            ]
        )
        return jsonify({"response": response.choices[0].message.content})

    except Exception as e:
        return jsonify({"response": f"Error: {str(e)}"})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))