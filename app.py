from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import os
import pandas as pd
from sqlalchemy import create_engine, text
from werkzeug.utils import secure_filename
from mistralai import Mistral
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import io
import base64

import matplotlib
matplotlib.use('Agg')

app = Flask(__name__)
app.secret_key = "analista_pro_final_2026"
app.config['UPLOAD_FOLDER'] = 'uploads'

# --- CONFIGURACIÓN ---
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "TU_MISTRAL_KEY")
client = Mistral(api_key=MISTRAL_API_KEY)
DATABASE_URL = os.environ.get("DATABASE_URL", "").replace("postgres://", "postgresql://", 1)
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=3600)

def inicializar_db():
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS suscripciones (
                email TEXT PRIMARY KEY,
                plan TEXT DEFAULT 'Mensual',
                fecha_vencimiento DATE DEFAULT (CURRENT_DATE + INTERVAL '30 days'),
                estado TEXT DEFAULT 'Activo',
                creditos_usados INTEGER DEFAULT 0
            );
        """))
        conn.commit()

def obtener_usuario(email):
    hoy = datetime.now().date()
    with engine.connect() as con:
        res = con.execute(text("SELECT * FROM suscripciones WHERE email = :e"), {"e": email}).fetchone()
        if not res: return None
        
        vence = res.fecha_vencimiento
        if hoy <= vence: estado = "Activo"
        elif hoy == vence + timedelta(days=1): estado = "Gracia"
        else: estado = "Vencido"
        
        return {"email": res.email, "vence": vence, "estado": estado, "creditos": res.creditos_usados}

@app.route('/')
def index():
    if 'user' not in session: return render_template('index.html', login_mode=True)
    user_data = obtener_usuario(session['user'])
    
    banner = None
    if user_data:
        if user_data['estado'] == "Gracia":
            banner = ("⚠️ Período de Gracia: Tu suscripción venció ayer.", "alert-warning")
        elif user_data['estado'] == "Vencido":
            banner = ("🚫 Suscripción Vencida: Acceso restringido.", "alert-danger")
            
    return render_template('index.html', login_mode=False, user=user_data, banner=banner)

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email').strip().lower()
    session['user'] = email
    with engine.connect() as con:
        con.execute(text("""
            INSERT INTO suscripciones (email, fecha_vencimiento) 
            VALUES (:e, CURRENT_DATE + INTERVAL '30 days') 
            ON CONFLICT (email) DO NOTHING
        """), {"e": email})
        con.commit()
    return redirect(url_for('index'))

@app.route('/admin')
def admin():
    with engine.connect() as con:
        usuarios = con.execute(text("SELECT * FROM suscripciones ORDER BY fecha_vencimiento DESC")).fetchall()
    return render_template('admin.html', usuarios=usuarios)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    inicializar_db()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))