from flask import Flask, request, jsonify, render_template, redirect, url_for, session
import os
import pandas as pd
from sqlalchemy import create_engine, text
from werkzeug.utils import secure_filename
from mistralai import Mistral
from datetime import datetime, timedelta
import gc

app = Flask(__name__)
app.secret_key = "secret_key_pro_analyst" # Cambia esto por algo seguro
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 

# --- CONFIGURACIÓN ---
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "TU_CLAVE_AQUÍ")
client = Mistral(api_key=MISTRAL_API_KEY)
model_mistral = "mistral-large-latest"

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def obtener_db_engine():
    DATABASE_URL = os.environ.get("DATABASE_URL", "")
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    return create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)

engine = obtener_db_engine()

# --- LÓGICA DE USUARIOS Y CRÉDITOS ---
def gestionar_usuario(email):
    """Obtiene o crea el usuario y gestiona el reinicio de créditos diarios."""
    hoy = datetime.now().date()
    try:
        with engine.connect() as con:
            query = text('SELECT creditos_usados, fecha_inicio, ultimo_uso FROM "suscripciones" WHERE email = :email')
            res = con.execute(query, {"email": email}).fetchone()
            
            if not res:
                # Crear usuario nuevo si no existe
                with con.begin():
                    con.execute(text('''
                        INSERT INTO "suscripciones" (email, creditos_usados, fecha_inicio, ultimo_uso, plan) 
                        VALUES (:email, 0, :hoy, :hoy, 'Pro Analyst')
                    '''), {"email": email, "hoy": hoy})
                return {"creditos": 0, "inicio": hoy}
            
            # Reinicio diario de créditos
            if res.ultimo_uso != hoy:
                with con.begin():
                    con.execute(text('UPDATE "suscripciones" SET creditos_usados = 0, ultimo_uso = :hoy WHERE email = :email'), 
                                {"hoy": hoy, "email": email})
                return {"creditos": 0, "inicio": res.fecha_inicio}
            
            return {"creditos": res.creditos_usados, "inicio": res.fecha_inicio}
    except Exception as e:
        print(f"Error DB Usuario: {e}")
        return {"creditos": 0, "inicio": hoy}

def registrar_uso_credito(email):
    try:
        with engine.connect() as con:
            with con.begin():
                con.execute(text('UPDATE "suscripciones" SET creditos_usados = creditos_usados + 1 WHERE email = :email'), 
                            {"email": email})
    except Exception as e:
        print(f"Error al registrar crédito: {e}")

# --- RUTAS ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        session['user_email'] = request.form.get('email')
        return redirect(url_for('index'))
    return '''
        <form method="post" style="text-align:center; margin-top:100px;">
            <input type="email" name="email" placeholder="Introduce tu email" required>
            <button type="submit">Entrar al Analista</button>
        </form>
    '''

@app.route('/')
def index():
    if 'user_email' not in session:
        return redirect(url_for('login'))
    
    datos = gestionar_usuario(session['user_email'])
    vencimiento = datetime(2025, 12, 30).date()
    hoy = datetime.now().date()
    
    mensaje_banner, clase_banner = None, None
    if hoy == vencimiento:
        mensaje_banner, clase_banner = "¡Tu suscripción vence hoy!", "banner-warning"
    elif hoy == vencimiento + timedelta(days=1):
        mensaje_banner, clase_banner = "Tu suscripción venció ayer (Día de Gracia).", "banner-danger"

    dias_prueba = (hoy - datos["inicio"]).days
    return render_template('index.html', 
                           creditos=datos["creditos"], 
                           dia_actual=max(0, dias_prueba),
                           banner_msj=mensaje_banner, 
                           banner_clase=clase_banner)

@app.route('/chat', methods=['POST'])
def chat():
    if 'user_email' not in session:
        return jsonify({"reply": "Por favor, inicia sesión."})

    try:
        data = request.json
        user_message = data.get("message")
        
        # Verificar límite diario
        stats = gestionar_usuario(session['user_email'])
        if stats["creditos"] >= 10:
            return jsonify({"reply": "🚫 Límite diario de 10 consultas alcanzado. ¡Vuelve mañana! 🚀"})

        with engine.connect() as conn:
            df_contexto = pd.read_sql(text('SELECT * FROM ventas LIMIT 40'), conn)
            resumen_datos = df_contexto.to_string(index=False)

        prompt_final = f"Datos reales:\n{resumen_datos}\nPregunta: {user_message}\nEres Visionary AI 🚀."
        chat_response = client.chat.complete(model=model_mistral, messages=[{"role": "user", "content": prompt_final}])
        
        registrar_uso_credito(session['user_email'])
        return jsonify({"reply": chat_response.choices[0].message.content})
    except Exception as e:
        return jsonify({"reply": "Sube un archivo primero para poder analizar."})

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files: return jsonify({"success": False}), 400
    file = request.files['file']
    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    try:
        file.save(file_path)
        df = pd.read_csv(file_path) if filename.endswith('.csv') else pd.read_excel(file_path)
        
        # Detección de industria universal
        prompt = f"Columnas: {df.columns.tolist()}. Define la industria en 1 palabra."
        res_ia = client.chat.complete(model=model_mistral, messages=[{"role": "user", "content": prompt}])
        contexto = res_ia.choices[0].message.content.strip()

        with engine.begin() as connection:
            df.to_sql('ventas', con=connection, if_exists='replace', index=False)
        
        del df
        if os.path.exists(file_path): os.remove(file_path)
        gc.collect()
        return jsonify({"success": True, "contexto": contexto})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)