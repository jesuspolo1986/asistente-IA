from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import os
import pandas as pd
import io
import base64
import matplotlib
matplotlib.use('Agg') # Optimizado para servidores
import matplotlib.pyplot as plt
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from mistralai import Mistral

app = Flask(__name__)
app.secret_key = "analista_pro_v3_predictivo"
app.config['UPLOAD_FOLDER'] = 'uploads'

# --- CONFIGURACIÓN DE ENTORNO ---
DATABASE_URL = os.environ.get("DATABASE_URL", "").replace("postgres://", "postgresql://", 1)
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")

engine = create_engine(DATABASE_URL, pool_size=5, max_overflow=10, pool_pre_ping=True)
client = Mistral(api_key=MISTRAL_API_KEY)

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
    
    # Lógica de Gracia Personalizada
    if hoy <= vence: 
        estado = "Activo"
    elif hoy == vence + timedelta(days=1): 
        estado = "Gracia"
        banner = ("⚠️ Recordatorio: Tu suscripción expiró ayer. Tienes un día de gracia.", "alert-warning")
    else: 
        estado = "Vencido"
        banner = ("🚫 Suscripción expirada. Por favor, renueva para continuar.", "alert-danger")
        
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
    if 'file' not in request.files: return jsonify({"error": "No hay archivo"}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({"error": "Sin nombre"}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    session['last_file'] = filename
    return jsonify({"success": True, "message": f"Análisis de '{filename}' listo."})

@app.route('/chat', methods=['POST'])
def chat():
    user_msg = request.json.get('message', '').lower()
    filename = session.get('last_file')
    email = session.get('user')
    
    if not filename:
        return jsonify({"response": "Sube un archivo primero para poder analizarlo."})

    try:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        df = pd.read_csv(filepath) if filename.endswith('.csv') else pd.read_excel(filepath)
        
        # --- MOTOR DE INTELIGENCIA PREDICTIVA ---
        # Creamos un resumen para que la IA tenga contexto total sin gastar tokens en 1000 filas
        resumen_texto = df.describe(include='all').to_string()
        primeras_filas = df.head(10).to_string()

        prompt_sistema = f"""
        ERES: Un Analista de Datos Predictivo Senior. 
        ARCHIVO: {filename}
        DATOS CLAVE (Resumen): {resumen_texto}
        MUESTRA: {primeras_filas}

        TAREA:
        1. Analiza la pregunta del usuario usando los datos proporcionados.
        2. NO des explicaciones de código ni menciones a Pandas/Python.
        3. Da hallazgos directos y PREDICCIONES basadas en tendencias observadas.
        4. Si detectas anomalías (bajas ventas, altos costos), menciónalas proactivamente.
        """
        
        # Generar Gráfico Automático si se detecta intención
        chart_b64 = None
        if any(word in user_msg for word in ["gráfico", "visualiza", "dibuja", "barras"]):
            plt.figure(figsize=(10, 5))
            # Selecciona automáticamente columnas numéricas para graficar
            df.select_dtypes(include=['number']).sum().plot(kind='bar', color='#3b82f6')
            plt.title("Análisis Visual Automático")
            plt.xticks(rotation=45)
            plt.tight_layout()
            
            buf = io.BytesIO()
            plt.savefig(buf, format='png')
            buf.seek(0)
            chart_b64 = base64.b64encode(buf.getvalue()).decode()
            plt.close()

        # Respuesta de IA
        response = client.chat.complete(
            model="mistral-small",
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": user_msg}
            ]
        )
        
        # Actualizar créditos
        with engine.connect() as conn:
            conn.execute(text("UPDATE suscripciones SET creditos_usados = creditos_usados + 1 WHERE email = :e"), {"e": email})
            conn.commit()

        return jsonify({
            "response": response.choices[0].message.content,
            "chart": chart_b64
        })

    except Exception as e:
        return jsonify({"response": f"Ocurrió un error analizando el archivo: {str(e)}"})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))