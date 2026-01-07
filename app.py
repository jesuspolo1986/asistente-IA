from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, scoped_session
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "analista_pro_final_2026"

# --- CONFIGURACIÓN DE DB SEGURA ---
DATABASE_URL = os.environ.get("DATABASE_URL", "").replace("postgres://", "postgresql://", 1)
engine = create_engine(DATABASE_URL, pool_size=5, max_overflow=10, pool_pre_ping=True)

# Scoped Session: Garantiza que cada petición tenga su propia conexión limpia
db_session = scoped_session(sessionmaker(bind=engine))

def obtener_estado_suscripcion(email):
    # La sesión se abre y se cierra automáticamente con el bloque try/finally
    try:
        res = db_session.execute(text("SELECT fecha_vencimiento FROM suscripciones WHERE email = :e"), {"e": email}).fetchone()
        if not res: return "Inexistente"
        
        hoy = datetime.now().date()
        vence = res.fecha_vencimiento
        
        if hoy <= vence: return "Activo"
        if hoy == vence + timedelta(days=1): return "Gracia" # Lógica de día de gracia [cite: 2025-12-30]
        return "Vencido"
    finally:
        db_session.remove() # LIMPIEZA OBLIGATORIA

@app.route('/')
def index():
    if 'user' not in session: return render_template('index.html', login_mode=True)
    estado = obtener_estado_suscripcion(session['user'])
    return render_template('index.html', login_mode=False, user=session['user'], estado=estado)

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email').strip().lower()
    session['user'] = email
    try:
        db_session.execute(text("""
            INSERT INTO suscripciones (email, fecha_vencimiento) 
            VALUES (:e, CURRENT_DATE + INTERVAL '30 days') 
            ON CONFLICT (email) DO NOTHING
        """), {"e": email})
        db_session.commit()
    except Exception as e:
        db_session.rollback()
        print(f"Error en login: {e}")
    finally:
        db_session.remove()
    return redirect(url_for('index'))

@app.teardown_appcontext
def shutdown_session(exception=None):
    # Este es el guardián final: si Flask olvida cerrar una conexión, esto la cierra.
    db_session.remove()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))