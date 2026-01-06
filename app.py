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

# Configuración de Matplotlib para ejecución en servidor
import matplotlib
matplotlib.use('Agg')

app = Flask(__name__)
app.secret_key = "analista_pro_final_2026"
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- CONFIGURACIÓN DE APIS Y DB ---
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "TU_MISTRAL_KEY")
client = Mistral(api_key=MISTRAL_API_KEY)

DATABASE_URL = os.environ.get("DATABASE_URL", "").replace("postgres://", "postgresql://", 1)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# --- LÓGICA DE BASE DE DATOS ---
def inicializar_db():
    """Crea las tablas necesarias con la nueva estructura de suscripción"""
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS public.suscripciones (
                email TEXT PRIMARY KEY,
                plan TEXT DEFAULT 'Mensual',
                fecha_vencimiento DATE DEFAULT (CURRENT_DATE + INTERVAL '30 days'),
                estado TEXT DEFAULT 'Activo',
                creditos_usados INTEGER DEFAULT 0,
                ultimo_uso DATE DEFAULT CURRENT_DATE
            );
        """))

def obtener_info_usuario(email):
    """Calcula el estado real del usuario basado en la fecha actual"""
    hoy = datetime.now().date()
    with engine.connect() as con:
        res = con.execute(text("""
            SELECT fecha_vencimiento, creditos_usados, estado 
            FROM public.suscripciones WHERE email = :e
        """), {"e": email}).fetchone()
        
        if not res: return None
        
        vencimiento = res.fecha_vencimiento
        # Lógica de Período de Gracia (Día 31)
        if hoy <= vencimiento:
            estado_real = "Activo"
        elif hoy == vencimiento + timedelta(days=1):
            estado_real = "Gracia"
        else:
            estado_real = "Vencido"
            
        return {
            "vencimiento": vencimiento,
            "creditos": res.creditos_usados,
            "estado": estado_real
        }

# --- MOTOR DE GRÁFICOS ---
def generar_grafico_visual(df):
    plt.figure(figsize=(8, 5))
    plt.style.use('ggplot')
    cols = {c.lower(): c for c in df.columns}
    
    if 'vendedor' in cols and 'total' in cols:
        data = df.groupby(cols['vendedor'])[cols['total']].sum().sort_values(ascending=False).head(5)
        data.plot(kind='bar', color='#4e73df')
        plt.title('Top 5 Ventas por Vendedor')
    elif 'conductor' in cols and 'costo_combustible' in cols:
        df['eficiencia'] = df[cols['costo_combustible']] / df[cols.get('kilometros', cols.get('kilómetros'))]
        data = df.groupby(cols['conductor'])['eficiencia'].mean().sort_values()
        data.plot(kind='barh', color='#1cc88a')
        plt.title('Eficiencia (€/km) por Conductor')
    else:
        df.select_dtypes(include=['number']).sum().plot(kind='pie', autopct='%1.1f%%')
        plt.title('Distribución General')

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    return base64.b64encode(buf.getvalue()).decode('utf-8')

# --- RUTAS DE LA APLICACIÓN ---

@app.route('/')
def index():
    if 'user' not in session: return render_template('index.html', login_mode=True)
    
    info = obtener_info_usuario(session['user'])
    if not info: return redirect(url_for('logout'))
    
    banner = None
    if info['estado'] == "Gracia":
        banner = ("⚠️ Tu suscripción venció ayer. Tienes 24h de gracia para renovar.", "banner-warning")
    elif info['estado'] == "Vencido":
        banner = ("🚫 Acceso bloqueado. Tu suscripción ha vencido.", "banner-danger")
        
    return render_template('index.html', login_mode=False, 
                           user=session['user'], creditos=info['creditos'], 
                           banner=banner, estado=info['estado'])

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email').strip().lower()
    session['user'] = email
    # Crear usuario si no existe
    with engine.begin() as con:
        con.execute(text("""
            INSERT INTO public.suscripciones (email, fecha_vencimiento) 
            VALUES (:e, :d) ON CONFLICT (email) DO NOTHING
        """), {"e": email, "d": datetime.now().date() + timedelta(days=30)})
    return redirect(url_for('index'))

@app.route('/admin')
def admin():
    # En producción, protege esta ruta
    with engine.connect() as con:
        usuarios = con.execute(text("SELECT * FROM public.suscripciones")).fetchall()
    return render_template('admin.html', usuarios=usuarios)

@app.route('/upload', methods=['POST'])
def upload():
    info = obtener_info_usuario(session.get('user'))
    if info['estado'] == "Vencido": return jsonify({"success": False, "message": "Suscripción vencida"})

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
    info = obtener_info_usuario(session.get('user'))
    if info['estado'] == "Vencido": return jsonify({"reply": "Tu acceso está bloqueado por falta de pago."})

    try:
        with engine.connect() as conn:
            df = pd.read_sql(text("SELECT * FROM public.ventas LIMIT 100"), conn)
        
        prompt = f"Actúa como Analista Senior. Datos: {df.to_string()}\nPregunta: {request.json['message']}"
        resp = client.chat.complete(model="mistral-large-latest", messages=[{"role": "user", "content": prompt}])
        
        grafico = generar_grafico_visual(df)

        with engine.begin() as con:
            con.execute(text('UPDATE public.suscripciones SET creditos_usados = creditos_usados + 1 WHERE email = :e'), {"e": session['user']})
            
        return jsonify({"reply": resp.choices[0].message.content, "chart": grafico})
    except Exception as e:
        return jsonify({"reply": f"Error: {str(e)}"})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    inicializar_db()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))