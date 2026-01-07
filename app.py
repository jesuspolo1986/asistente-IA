from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import os
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "analista_pro_final_2026"

# --- CONFIGURACIÓN DE DB ---
DATABASE_URL = os.environ.get("DATABASE_URL", "").replace("postgres://", "postgresql://", 1)
engine = create_engine(DATABASE_URL, pool_size=5, max_overflow=10, pool_pre_ping=True)

@app.route('/')
def index():
    if 'user' not in session: return render_template('index.html', login_mode=True)
    
    email = session['user']
    hoy = datetime.now().date()
    
    with engine.connect() as conn:
        res = conn.execute(text("SELECT fecha_vencimiento, creditos_usados FROM suscripciones WHERE email = :e"), {"e": email}).fetchone()
    
    if not res: return redirect(url_for('logout'))
    
    vence = res[0]
    usados = res[1] or 0
    
    # Lógica de estados y banners
    banner = None
    if hoy <= vence: 
        estado = "Activo"
    elif hoy == vence + timedelta(days=1): 
        estado = "Gracia"
        banner = ("⚠️ Período de Gracia: Tu suscripción venció ayer.", "alert-warning")
    else: 
        estado = "Vencido"
        banner = ("🚫 Suscripción Vencida. Acceso limitado.", "alert-danger")
        
    # Enviamos todas las variables que el HTML necesita para no dar error 500
    return render_template('index.html', 
                           login_mode=False, 
                           user=email, 
                           estado=estado, 
                           creditos=usados, 
                           banner=banner)

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

@app.route('/admin')
def admin():
    with engine.connect() as conn:
        usuarios = conn.execute(text("SELECT * FROM suscripciones")).fetchall()
    return render_template('admin.html', usuarios=usuarios)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))