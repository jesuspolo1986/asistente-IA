from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import os
import pandas as pd
from sqlalchemy import create_engine, text
from werkzeug.utils import secure_filename
from mistralai import Mistral
from datetime import datetime, timedelta
import gc

app = Flask(__name__)
app.secret_key = "clave_secreta_visionary"
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- CONFIGURACIÓN ---
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "TU_KEY")
client = Mistral(api_key=MISTRAL_API_KEY)
model_mistral = "mistral-large-latest"

# Conexión optimizada para evitar desconexiones
engine = create_engine(
    os.environ.get("DATABASE_URL", "").replace("postgres://", "postgresql://", 1),
    pool_pre_ping=True
)

def gestionar_creditos(email):
    hoy = datetime.now().date()
    try:
        with engine.connect() as con:
            # Importante: usar comillas dobles si la tabla tiene mayúsculas o es estricta
            query = text('SELECT creditos_usados, ultimo_uso FROM suscripciones WHERE email = :e')
            res = con.execute(query, {"e": email}).fetchone()
            
            if not res:
                with con.begin():
                    con.execute(text('INSERT INTO suscripciones (email, creditos_usados, ultimo_uso) VALUES (:e, 0, :h)'), {"e": email, "h": hoy})
                return 0
            
            if res.ultimo_uso != hoy:
                with con.begin():
                    con.execute(text('UPDATE suscripciones SET creditos_usados = 0, ultimo_uso = :h WHERE email = :e'), {"e": email, "h": hoy})
                return 0
            return res.creditos_usados
    except Exception as e:
        print(f"Error en gestionar_creditos: {e}")
        return 0

@app.route('/')
def index():
    if 'user' not in session: return render_template('index.html', login_mode=True)
    
    creditos = gestionar_creditos(session['user'])
    # Fecha de vencimiento según tus instrucciones (30 Dic 2025)
    vencimiento = datetime(2025, 12, 30).date()
    hoy = datetime.now().date()
    
    banner = None
    if hoy == vencimiento: 
        banner = ("¡Tu suscripción vence hoy!", "banner-warning")
    elif hoy == vencimiento + timedelta(days=1): 
        banner = ("Suscripción venció ayer (Día de Gracia)", "banner-danger")
    
    # Calculamos día de prueba (asumiendo inicio el 28 de dic como ejemplo)
    inicio = datetime(2025, 12, 28).date()
    dia_prueba = (hoy - inicio).days
    
    return render_template('index.html', 
                           login_mode=False, 
                           creditos=creditos, 
                           user=session['user'], 
                           banner=banner,
                           dia_actual=max(0, dia_prueba))

@app.route('/login', methods=['POST'])
def login():
    session['user'] = request.form.get('email')
    return redirect(url_for('index'))

@app.route('/chat', methods=['POST'])
def chat():
    user = session.get('user')
    if not user: return jsonify({"reply": "Sesión expirada."})
    
    creditos = gestionar_creditos(user)
    if creditos >= 10: 
        return jsonify({"reply": "🚫 Límite diario alcanzado (10/10). Vuelve mañana."})

    data = request.json
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text('SELECT * FROM ventas LIMIT 35'), conn)
        
        prompt = f"Datos actuales del archivo:\n{df.to_string()}\n\nPregunta: {data['message']}"
        resp = client.chat.complete(model=model_mistral, messages=[{"role": "user", "content": prompt}])
        
        # Incrementar crédito solo tras respuesta exitosa
        with engine.connect() as con:
            with con.begin():
                con.execute(text('UPDATE suscripciones SET creditos_usados = creditos_usados + 1 WHERE email = :e'), {"e": user})
                
        return jsonify({"reply": resp.choices[0].message.content})
    except Exception as e:
        return jsonify({"reply": "Sube un archivo primero o verifica la conexión."})
@app.route('/logout')
def logout():
    session.pop('user', None) # Elimina al usuario de la sesión
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
        
        # Detección de industria con IA
        prompt = f"Basado en estas columnas: {df.columns.tolist()}, ¿qué industria es? Responde en una palabra."
        res = client.chat.complete(model=model_mistral, messages=[{"role": "user", "content": prompt}])
        contexto = res.choices[0].message.content.strip()
        
        with engine.begin() as connection:
            df.to_sql('ventas', con=connection, if_exists='replace', index=False)
        
        if os.path.exists(path): os.remove(path) # Limpiar servidor
        return jsonify({"success": True, "contexto": contexto})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)