import os
import pandas as pd
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from mistralai import Mistral

app = Flask(__name__)
app.secret_key = "analista_pro_v5_monitoreo_total"
app.config['UPLOAD_FOLDER'] = 'uploads'

# --- CONFIGURACIÓN DE ENTORNO ---
DATABASE_URL = os.environ.get("DATABASE_URL", "").replace("postgres://", "postgresql://", 1)
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")

engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20)
client = Mistral(api_key=MISTRAL_API_KEY)

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# --- FUNCIÓN DE MONITOREO (LOGS) ---
def registrar_log(email, accion, detalle):
    try:
        with engine.connect() as conn:
            conn.execute(text("INSERT INTO logs_actividad (email, accion, detalle) VALUES (:e, :a, :d)"),
                         {"e": email, "a": accion, "d": detalle})
            conn.commit()
    except Exception as e:
        print(f"Error al registrar log: {e}")

# --- RUTAS PRINCIPALES ---
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
    if hoy <= vence: 
        estado = "Activo"
    elif hoy == vence + timedelta(days=1): 
        estado = "Gracia"
        banner = ("⚠️ Tu suscripción venció ayer. Hoy es tu último día de gracia.", "alert-warning")
    else: 
        estado = "Vencido"
        banner = ("🚫 Suscripción expirada. Acceso restringido.", "alert-danger")
    
    return render_template('index.html', login_mode=False, user=email, estado=estado, creditos=usados, banner=banner)

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email').strip().lower()
    session['user'] = email
    with engine.connect() as conn:
        conn.execute(text("INSERT INTO suscripciones (email, fecha_vencimiento) VALUES (:e, CURRENT_DATE + INTERVAL '30 days') ON CONFLICT (email) DO NOTHING"), {"e": email})
        conn.commit()
    registrar_log(email, "LOGIN", "El usuario ingresó al sistema")
    return redirect(url_for('index'))

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files.get('file')
    if not file: return jsonify({"error": "No file"}), 400
    email = session.get('user', 'unknown')
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    session['last_file'] = filename
    registrar_log(email, "UPLOAD", f"Subió el archivo: {filename}")
    return jsonify({"success": True})

# --- MOTOR DE CHAT CON VISIÓN TOTAL ---
@app.route('/chat', methods=['POST'])
def chat():
    user_msg = request.json.get('message', '').lower()
    email = session.get('user', 'unknown')
    filename = session.get('last_file')
    if not filename: return jsonify({"response": "Sube un archivo primero."})

    try:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        df = pd.read_csv(filepath) if filename.endswith('.csv') else pd.read_excel(filepath)
        
        # --- DETECTOR UNIVERSAL DE COLUMNAS ---
        cols = df.columns.tolist()
        col_sujeto = next((c for c in cols if c.lower() in ['vendedor', 'conductor', 'tienda', 'sku', 'empleado', 'departamento']), cols[0])
        col_valor = next((c for c in cols if c.lower() in ['total', 'ventas_netas', 'kilometros', 'monto', 'sueldo', 'cantidad']), cols[-1])
        
        # --- CÁLCULOS DINÁMICOS ---
        ranking = df.groupby(col_sujeto)[col_valor].sum().sort_values(ascending=False)
        muestra_dict = df.head(10).to_dict(orient='records')

        contexto_servidor = f"""
        [ESTRUCTURA]
        Columnas: {cols}
        Muestra Datos: {muestra_dict}
        [RANKING]
        Líder en {col_valor}: {ranking.index[0]} con {ranking.iloc[0]:,.2f}
        Todos: {ranking.to_dict()}
        """

        # INTERCEPTOR DE SEGURIDAD (Cálculos directos de Python)
        if any(w in user_msg for w in ["mejor", "ganador", "mas vendio", "lider"]):
             res_directo = f"📊 **Monitor:** El líder en {col_sujeto} es {ranking.index[0]} con {ranking.iloc[0]:,.2f}."
             registrar_log(email, "CHAT_AUTO", f"Pregunta: {user_msg} | Resp: Liderazgo")
             return jsonify({"response": res_directo})

        # LLAMADA A IA
        response = client.chat.complete(
            model="mistral-small",
            temperature=0,
            messages=[
                {"role": "system", "content": f"Eres un Analista Experto. Datos: {contexto_servidor}. Si no encuentras un dato, di que no está en este archivo."},
                {"role": "user", "content": user_msg}
            ]
        )
        respuesta_ia = response.choices[0].message.content
        registrar_log(email, "CHAT_IA", f"Pregunta: {user_msg}")
        
        return jsonify({"response": respuesta_ia})

    except Exception as e:
        registrar_log(email, "ERROR", str(e))
        return jsonify({"response": f"Error técnico: {str(e)}"})

# --- PANEL ADMIN CON MONITOREO TOTAL ---
@app.route('/admin')
def admin_panel():
    hoy = datetime.now().date()
    with engine.connect() as conn:
        # 1. Obtener Usuarios
        users_res = conn.execute(text("SELECT email, fecha_vencimiento, creditos_usados FROM suscripciones")).fetchall()
        # 2. Obtener Logs de Actividad (últimos 20)
        logs_res = conn.execute(text("SELECT email, accion, detalle, fecha FROM logs_actividad ORDER BY fecha DESC LIMIT 20")).fetchall()
    
    users_list = []
    stats = {"total": 0, "gracia": 0, "expirados": 0, "consultas": 0}
    
    for u in users_res:
        vence = u[1]
        clase = "badge-active"
        if hoy > vence + timedelta(days=1): 
            clase = "badge-expired"; stats["expirados"] += 1
        elif hoy > vence: 
            clase = "badge-grace"; stats["gracia"] += 1
        
        users_list.append({"email": u[0], "vence": vence, "creditos": u[2] or 0, "clase": clase})
        stats["total"] += 1
        stats["consultas"] += (u[2] or 0)
        
    return render_template('admin.html', users=users_list, stats=stats, logs=logs_res)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))