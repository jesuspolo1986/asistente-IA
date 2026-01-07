from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import os
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "analista_pro_2026_key"

# --- CONFIGURACIÓN DE DB SEGURA ---
# Usamos pool_size=1 para que en el despliegue no saturemos las conexiones de Supabase
DATABASE_URL = os.environ.get("DATABASE_URL", "").replace("postgres://", "postgresql://", 1)
engine = create_engine(DATABASE_URL, pool_size=1, max_overflow=0, pool_pre_ping=True)

@app.route('/')
def index():
    if 'user' not in session: return render_template('index.html', login_mode=True)
    
    email = session['user']
    hoy = datetime.now().date()
    
    # Abrimos conexión, consultamos y cerramos inmediatamente
    with engine.connect() as conn:
        res = conn.execute(text("SELECT fecha_vencimiento FROM suscripciones WHERE email = :e"), {"e": email}).fetchone()
        
    if not res: return redirect(url_for('logout'))
    
    vence = res[0]
    # Lógica de estados para el banner [cite: 2025-12-30]
    if hoy <= vence: estado = "Activo"
    elif hoy == vence + timedelta(days=1): estado = "Gracia"
    else: estado = "Vencido"
        
    return render_template('index.html', login_mode=False, user=email, estado=estado)

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email').strip().lower()
    session['user'] = email
    
    with engine.connect() as conn:
        # Usamos execute directo sin bloques begin() para evitar el error de transacción
        conn.execute(text("""
            INSERT INTO suscripciones (email, fecha_vencimiento) 
            VALUES (:e, CURRENT_DATE + INTERVAL '30 days') 
            ON CONFLICT (email) DO NOTHING
        """), {"e": email})
        conn.commit() # Confirmación manual
        
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    # No inicializamos la DB aquí para evitar colisiones en el arranque de Koyeb
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))