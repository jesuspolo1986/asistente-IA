from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import os
import pandas as pd
from sqlalchemy import create_engine, text
from werkzeug.utils import secure_filename
from mistralai import Mistral
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "clave_secreta_visionary"
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "TU_KEY_AQUI")
client = Mistral(api_key=MISTRAL_API_KEY)
model_mistral = "mistral-large-latest"

engine = create_engine(os.environ.get("DATABASE_URL", "").replace("postgres://", "postgresql://", 1), pool_pre_ping=True)

def gestionar_creditos(email):
    hoy = datetime.now().date()
    try:
        with engine.connect() as con:
            # Usamos comillas dobles en "suscripciones" para evitar el error de relación
            res = con.execute(text('SELECT creditos_usados, ultimo_uso FROM "suscripciones" WHERE email = :e'), {"e": email}).fetchone()
            if not res:
                with con.begin():
                    con.execute(text('INSERT INTO "suscripciones" (email, creditos_usados, ultimo_uso) VALUES (:e, 0, :h)'), {"e": email, "h": hoy})
                return 0
            if res.ultimo_uso != hoy:
                with con.begin():
                    con.execute(text('UPDATE "suscripciones" SET creditos_usados = 0, ultimo_uso = :h WHERE email = :e'), {"e": email, "h": hoy})
                return 0
            return res.creditos_usados
    except Exception as e:
        print(f"Error Crítico DB: {e}")
        return 0

@app.route('/')
def index():
    if 'user' not in session: return render_template('index.html', login_mode=True)
    creditos = gestionar_creditos(session['user'])
    return render_template('index.html', login_mode=False, creditos=creditos, user=session['user'])

@app.route('/login', methods=['POST'])
def login():
    session['user'] = request.form.get('email').strip().lower()
    return redirect(url_for('index'))

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files['file']
    filename = secure_filename(file.filename)
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(path)
    try:
        df = pd.read_csv(path) if filename.endswith('.csv') else pd.read_excel(path)
        with engine.begin() as connection:
            # Reemplazamos la tabla "ventas" completamente
            df.to_sql('ventas', con=connection, if_exists='replace', index=False)
        return jsonify({"success": True, "contexto": "Archivo procesado"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/chat', methods=['POST'])
def chat():
    user = session.get('user')
    creditos = gestionar_creditos(user)
    if creditos >= 10: return jsonify({"reply": "Límite de 10/10 alcanzado."})

    try:
        with engine.connect() as conn:
            # SOLUCIÓN UNIVERSAL: Cargamos los datos en Pandas para evitar errores de SQL
            df = pd.read_sql(text('SELECT * FROM "ventas" LIMIT 50'), conn)
        
        data = request.json
        # Le enviamos el DataFrame a la IA para que ella busque las columnas (sin importar mayúsculas)
        prompt = f"Datos:\n{df.to_string()}\n\nPregunta: {data['message']}"
        resp = client.chat.complete(model=model_mistral, messages=[{"role": "user", "content": prompt}])
        
        with engine.begin() as con:
            con.execute(text('UPDATE "suscripciones" SET creditos_usados = creditos_usados + 1 WHERE email = :e'), {"e": user})
            
        return jsonify({"reply": resp.choices[0].message.content})
    except Exception as e:
        return jsonify({"reply": "⚠️ Error: Sube el archivo de nuevo. La tabla no está lista."})
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)