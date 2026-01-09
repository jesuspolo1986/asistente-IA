from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import os
import pandas as pd
import io
import base64
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from mistralai import Mistral

app = Flask(__name__)
app.secret_key = "analista_pro_v4_ultra_senior_fixed"
app.config['UPLOAD_FOLDER'] = 'uploads'

# --- CONFIGURACIÓN DE ENTORNO ---
DATABASE_URL = os.environ.get("DATABASE_URL", "").replace("postgres://", "postgresql://", 1)
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")

engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20)
client = Mistral(api_key=MISTRAL_API_KEY)

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# --- RUTAS DE USUARIO Y SUSCRIPCIÓN ---
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
    return redirect(url_for('index'))

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files.get('file')
    if not file: return jsonify({"error": "No file"}), 400
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    session['last_file'] = filename
    return jsonify({"success": True})

# --- MOTOR DE CHAT SENIOR CON AUDITORÍA ---
@app.route('/chat', methods=['POST'])
def chat():
    user_msg = request.json.get('message', '').lower()
    filename = session.get('last_file')
    if not filename: return jsonify({"response": "Sube un archivo primero."})

    try:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        df = pd.read_csv(filepath) if filename.endswith('.csv') else pd.read_excel(filepath)
        
        # --- AUDITORÍA AUTOMÁTICA (DINÁMICA) ---
        # 1. Ranking Dinero
        ranking_dinero = df.groupby('Vendedor')['Total'].sum().sort_values(ascending=False)
        # 2. Ranking Unidades
        ranking_unidades = df.groupby('Vendedor')['Cantidad'].sum().sort_values(ascending=False)
        # 3. Producto Estrella
        top_prod = df.groupby('Producto')['Cantidad'].sum().idxmax()

        # CONSTRUIR EL "MAPA DE VERDAD" PARA LA IA
        contexto_servidor = f"""
        [DATOS REALES DEL ARCHIVO]
        - LÍDER DINERO: {ranking_dinero.index[0]} (${ranking_dinero.iloc[0]:,.2f})
        - LÍDER UNIDADES: {ranking_unidades.index[0]} ({ranking_unidades.iloc[0]} unidades)
        - PRODUCTO MÁS VENDIDO: {top_prod}
        
        DETALLE DE UNIDADES POR VENDEDOR:
        {ranking_unidades.to_string()}
        [/DATOS REALES]
        """

        # INTERCEPTOR PARA EL MEJOR VENDEDOR (DINERO)
        if "mejor vendedor" in user_msg or "vendio mas" in user_msg:
            if "unidades" not in user_msg and "cantidad" not in user_msg:
                return jsonify({"response": f"📊 **Análisis:** El mejor vendedor por ingresos es **{ranking_dinero.index[0]}** con **${ranking_dinero.iloc[0]:,.2f}**."})

        # IA PARA ANÁLISIS COMPLEJO
        response = client.chat.complete(
            model="mistral-small",
            temperature=0,
            messages=[
                {"role": "system", "content": f"Eres un Analista Experto. Usa estos datos: {contexto_servidor}. Si te preguntan algo que no está aquí, di que no tienes el dato, pero NO inventes."},
                {"role": "user", "content": user_msg}
            ]
        )
        return jsonify({"response": response.choices[0].message.content})

    except Exception as e:
        return jsonify({"response": f"Error: {str(e)}"})
@app.route('/admin')
def admin_panel():
    hoy = datetime.now().date()
    with engine.connect() as conn:
        res = conn.execute(text("SELECT email, fecha_vencimiento, creditos_usados FROM suscripciones")).fetchall()
    
    users_list = []
    stats = {"total": 0, "gracia": 0, "expirados": 0, "consultas": 0}
    
    for u in res:
        vence = u[1]
        clase = "badge-active"
        if hoy > vence + timedelta(days=1): 
            clase = "badge-expired"; stats["expirados"] += 1
        elif hoy > vence: 
            clase = "badge-grace"; stats["gracia"] += 1
        
        users_list.append({"email": u[0], "vence": vence, "creditos": u[2] or 0, "clase": clase})
        stats["total"] += 1
        stats["consultas"] += (u[2] or 0)
        
    return render_template('admin.html', users=users_list, stats=stats)

@app.route('/admin/extend', methods=['POST'])
def extend_user():
    email = request.form.get('email')
    with engine.connect() as conn:
        conn.execute(text("UPDATE suscripciones SET fecha_vencimiento = CURRENT_DATE + INTERVAL '30 days' WHERE email = :e"), {"e": email})
        conn.commit()
    return redirect(url_for('admin_panel'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))
    #