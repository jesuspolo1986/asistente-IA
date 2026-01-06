from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import os
import pandas as pd
from sqlalchemy import create_engine, text
from werkzeug.utils import secure_filename
from mistralai import Mistral
from datetime import datetime
import matplotlib.pyplot as plt
import io
import base64

# Configuración de Matplotlib para servidores (sin interfaz gráfica)
import matplotlib
matplotlib.use('Agg')

app = Flask(__name__)
app.secret_key = "analista_pro_final_2026"
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- CONFIGURACIÓN ---
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "TU_MISTRAL_KEY")
client = Mistral(api_key=MISTRAL_API_KEY)

DATABASE_URL = os.environ.get("DATABASE_URL", "").replace("postgres://", "postgresql://", 1)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

def inicializar_db():
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS public.suscripciones (
                email TEXT PRIMARY KEY,
                creditos_usados INTEGER DEFAULT 0,
                ultimo_uso DATE DEFAULT CURRENT_DATE
            );
        """))

def gestionar_creditos(email):
    hoy = datetime.now().date()
    try:
        with engine.connect() as con:
            res = con.execute(text('SELECT creditos_usados, ultimo_uso FROM public.suscripciones WHERE email = :e'), {"e": email}).fetchone()
            if not res:
                with con.begin():
                    con.execute(text('INSERT INTO public.suscripciones (email, creditos_usados, ultimo_uso) VALUES (:e, 0, :h)'), {"e": email, "h": hoy})
                return 0
            if res.ultimo_uso != hoy:
                with con.begin():
                    con.execute(text('UPDATE public.suscripciones SET creditos_usados = 0, ultimo_uso = :h WHERE email = :e'), {"e": email, "h": hoy})
                return 0
            return res.creditos_usados
    except Exception as e:
        print(f"Error DB: {e}")
        return 0

# --- NUEVA FUNCIÓN: MOTOR DE GRÁFICOS PROFESIONALES ---
def generar_grafico_visual(df, tipo_analisis):
    plt.figure(figsize=(8, 5))
    plt.style.use('ggplot') # Estilo profesional
    
    if 'vendedor' in df.columns and 'total' in df.columns:
        data = df.groupby('vendedor')['total'].sum().sort_values(ascending=False).head(5)
        data.plot(kind='bar', color=['#4e73df', '#1cc88a', '#36b9cc', '#f6c23e', '#e74a3b'])
        plt.title('Top 5 Ventas por Vendedor')
        plt.ylabel('Monto Total')
    elif 'conductor' in df.columns and 'costo_combustible' in df.columns:
        df['eficiencia'] = df['costo_combustible'] / df['kilometros']
        data = df.groupby('conductor')['eficiencia'].mean().sort_values()
        data.plot(kind='barh', color='#36b9cc')
        plt.title('Eficiencia por Conductor (€/km) - Menor es mejor')
    else:
        # Gráfico genérico para otros tipos de datos
        df.iloc[:, 0:2].set_index(df.columns[0]).plot(kind='pie', subplots=True, autopct='%1.1f%%')
        plt.title('Distribución de Datos')

    plt.tight_layout()
    
    # Convertir a imagen para la web
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    img_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    plt.close()
    return img_base64

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
        df.columns = [str(c).strip().lower() for c in df.columns]
        with engine.begin() as connection:
            df.to_sql('ventas', con=connection, if_exists='replace', index=False, schema='public')
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/chat', methods=['POST'])
def chat():
    user = session.get('user')
    creditos = gestionar_creditos(user)
    if creditos >= 10: return jsonify({"reply": "Límite diario alcanzado."})

    try:
        with engine.connect() as conn:
            df = pd.read_sql(text("SELECT * FROM public.ventas LIMIT 100"), conn)
        
        data = request.json
        prompt = f"""Actúa como un Analista Senior (AI Pro Analyst).
        Analiza estos datos: {df.to_string()}
        Pregunta: {data['message']}
        Instrucciones: Da una respuesta ejecutiva, con hallazgos y recomendaciones estratégicas."""
        
        resp = client.chat.complete(model="mistral-large-latest", messages=[{"role": "user", "content": prompt}])
        
        # Generamos el gráfico basado en los datos cargados
        grafico = generar_grafico_visual(df, data['message'])

        with engine.begin() as con:
            con.execute(text('UPDATE public.suscripciones SET creditos_usados = creditos_usados + 1 WHERE email = :e'), {"e": user})
            
        return jsonify({
            "reply": resp.choices[0].message.content,
            "chart": grafico  # Enviamos el gráfico base64 a la interfaz
        })
    except Exception as e:
        return jsonify({"reply": f"Error: {str(e)}"})

if __name__ == '__main__':
    try: inicializar_db()
    except: pass
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))