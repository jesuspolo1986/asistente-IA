from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import os
import pandas as pd
import io
import base64
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from mistralai import Mistral

app = Flask(__name__)
app.secret_key = "analista_pro_v4_ultra_senior_fixed"
app.config['UPLOAD_FOLDER'] = 'uploads'

# --- CONFIGURACIÓN DE ENTORNO ---
DATABASE_URL = os.environ.get("DATABASE_URL", "").replace("postgres://", "postgresql://", 1)
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")

engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20)
client = Mistral(api_key=MISTRAL_API_KEY)

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# --- RUTAS DE USUARIO Y SUSCRIPCIÓN ---
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
    return redirect(url_for('index'))

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files.get('file')
    if not file: return jsonify({"error": "No file"}), 400
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    session['last_file'] = filename
    return jsonify({"success": True})

# --- MOTOR DE CHAT SENIOR CON AUDITORÍA ---
@app.route('/chat', methods=['POST'])
def chat():
    user_msg = request.json.get('message', '').lower()
    filename = session.get('last_file')
    if not filename: return jsonify({"response": "Sube un archivo primero."})

    try:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        df = pd.read_csv(filepath) if filename.endswith('.csv') else pd.read_excel(filepath)
        
        # --- 1. IDENTIFICACIÓN DINÁMICA ---
        cols = df.columns.tolist()
        col_sujeto = next((c for c in cols if c.lower() in ['vendedor', 'conductor', 'tienda', 'sku', 'empleado', 'departamento']), cols[0])
        col_valor = next((c for c in cols if c.lower() in ['total', 'ventas_netas', 'kilometros', 'monto', 'sueldo', 'cantidad']), cols[-1])
        
        # --- 2. CÁLCULOS DE AUDITORÍA ---
        ranking = df.groupby(col_sujeto)[col_valor].sum().sort_values(ascending=False)
        # Muestra de datos para que la IA vea columnas secundarias (como SKU o Ruta)
        muestra_dict = df.head(10).to_dict(orient='records')

        # --- 3. MAPA DE VERDAD EXTENDIDO ---
        contexto_servidor = f"""
        [ESTRUCTURA]
        Columnas disponibles: {cols}
        Muestra de datos (JSON): {muestra_dict}
        
        [RANKING PRINCIPAL]
        Líder en {col_valor}: {ranking.index[0]} con {ranking.iloc[0]:,.2f}
        Todos los {col_sujeto}s: {ranking.to_dict()}
        [/DATOS REALES]
        """

        # IA CON VISIÓN TOTAL
        response = client.chat.complete(
            model="mistral-small",
            temperature=0,
            messages=[
                {"role": "system", "content": f"Eres un Analista Experto. Usa el [ESTRUCTURA] para saber qué columnas existen y el [RANKING] para cálculos rápidos. Si te preguntan por algo que está en la muestra pero no en el ranking (como un SKU específico), búscalo en la muestra. Si no existe en ningún lado, niégalo."},
                {"role": "user", "content": user_msg}
            ]
        )
        return jsonify({"response": response.choices[0].message.content})

    except Exception as e:
        return jsonify({"response": f"Error técnico: {str(e)}"})
@app.route('/admin')
def admin_panel():
    hoy = datetime.now().date()
    with engine.connect() as conn:
        res = conn.execute(text("SELECT email, fecha_vencimiento, creditos_usados FROM suscripciones")).fetchall()
    
    users_list = []
    stats = {"total": 0, "gracia": 0, "expirados": 0, "consultas": 0}
    
    for u in res:
        vence = u[1]
        clase = "badge-active"
        if hoy > vence + timedelta(days=1): 
            clase = "badge-expired"; stats["expirados"] += 1
        elif hoy > vence: 
            clase = "badge-grace"; stats["gracia"] += 1
        
        users_list.append({"email": u[0], "vence": vence, "creditos": u[2] or 0, "clase": clase})
        stats["total"] += 1
        stats["consultas"] += (u[2] or 0)
        
    return render_template('admin.html', users=users_list, stats=stats)

@app.route('/admin/extend', methods=['POST'])
def extend_user():
    email = request.form.get('email')
    with engine.connect() as conn:
        conn.execute(text("UPDATE suscripciones SET fecha_vencimiento = CURRENT_DATE + INTERVAL '30 days' WHERE email = :e"), {"e": email})
        conn.commit()
    return redirect(url_for('admin_panel'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))
def generar_grafico(df, col_x, col_y):
    plt.figure(figsize=(10, 6))
    df.groupby(col_x)[col_y].sum().sort_values().plot(kind='barh', color='skyblue')
    plt.title(f'Ranking de {col_y} por {col_x}')
    plt.tight_layout()
    
    # Guardar en buffer para enviar como imagen base64
    img = io.BytesIO()
    plt.savefig(img, format='png')
    img.seek(0)
    plot_url = base64.b64encode(img.getvalue()).decode()
    plt.close()
    return plot_url

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))
    #