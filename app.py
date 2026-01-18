import os
import io
import pandas as pd
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, send_file
from sqlalchemy import create_engine, text
from werkzeug.utils import secure_filename
from mistralai import Mistral
from rapidfuzz import process, utils
from datetime import datetime, date, timedelta

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "elena_pro_secret_2026")

# --- CONFIGURACIÓN DE DB Y SERVICIOS ---
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:aSxRZ3rVrMu2Oasu@db.kebpamfydhnxeaeegulx.supabase.co:6543/postgres")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
client = Mistral(api_key=os.environ.get("MISTRAL_API_KEY", "p2KCokd08zRypMAZQxMbC4ImxkM5DPK1"))

MAPEO_COLUMNAS = {
    'Producto': ['producto', 'descripcion', 'nombre', 'articulo', 'item'],
    'Precio Venta': ['precio venta', 'pvp', 'precio', 'venta', 'precio_unitario'],
    'Costo': ['costo', 'compra', 'p.costo'],
    'Stock Actual': ['stock actual', 'stock', 'cantidad', 'existencia']
}

# --- RUTAS DE NAVEGACIÓN ---

@app.route('/')
def index():
    if 'user' not in session:
        return render_template('index.html', login_mode=True)
    
    # Si está logueado, verificamos suscripción en Supabase
    with engine.connect() as conn:
        query = text("SELECT fecha_vencimiento, activo FROM suscripciones WHERE email = :e")
        user = conn.execute(query, {"e": session['user']}).mappings().fetchone()
    
    if user and user['activo'] == 1:
        # Aquí cargamos la interfaz de Elena (debes tener elena.html en /templates)
        tasa = session.get('tasa_actual', 36.50)
        return render_template('elena.html', user=session['user'], tasa=tasa)
    
    session.clear()
    return render_template('index.html', login_mode=True, error="Suscripción inactiva.")

# --- LÓGICA DE ELENA (BÚSQUEDA Y IA) ---

@app.route('/preguntar', methods=['POST'])
def preguntar():
    if 'user' not in session: return jsonify({"error": "No autorizado"}), 401
    
    data = request.json
    pregunta = data.get("pregunta", "").lower().strip()
    modo_admin = data.get("modo_admin", False)
    resumen = session.get('resumen_datos') # Aquí vive el DataFrame convertido a dict
    
    if not resumen:
        return jsonify({"respuesta": "Elena: No tengo un inventario cargado todavía."})

    # 1. Lógica de RapidFuzz para búsqueda exacta de productos
    df = pd.DataFrame(resumen['datos_completos'])
    lista_productos = df['Producto'].astype(str).tolist()
    
    match = process.extractOne(pregunta.replace("precio", "").strip(), lista_productos, processor=utils.default_process)
    
    if match and match[1] > 65:
        f = df[df['Producto'] == match[0]].iloc[0]
        tasa = session.get('tasa_actual', 36.50)
        p_usd = float(f['Precio Venta'])
        p_bs = p_usd * tasa
        
        if modo_admin:
            m = ((p_usd - f['Costo']) / p_usd) * 100 if p_usd > 0 else 0
            res = f"📊 {match[0]} | Costo: ${f['Costo']:.2f} | Venta: ${p_usd:.2f} | Margen: {m:.1f}% | Stock: {int(f['Stock Actual'])}"
        else:
            res = f"El {match[0]} tiene un costo de {p_bs:,.2f} Bolívares (o {p_usd:,.2f} Dólares)."
        
        # Consumir crédito en Supabase por la consulta exitosa
        actualizar_creditos(session['user'])
        return jsonify({"respuesta": res})

    # 2. Si no es un producto, usamos Mistral para responder de forma general
    return responder_con_ia(pregunta, resumen)

def actualizar_creditos(email):
    with engine.begin() as conn:
        conn.execute(text("UPDATE suscripciones SET creditos_usados = COALESCE(creditos_usados, 0) + 1 WHERE email = :e"), {"e": email})

def responder_con_ia(pregunta, resumen):
    prompt = f"Eres Elena, asistente de farmacia. Datos: {resumen['columnas']}. Responde: {pregunta}"
    response = client.chat.complete(model="mistral-small", messages=[{"role": "system", "content": prompt}, {"role": "user", "content": pregunta}])
    return jsonify({"respuesta": response.choices[0].message.content})

# --- CARGA DE ARCHIVOS ---

@app.route('/upload', methods=['POST'])
def upload():
    if 'user' not in session: return jsonify({"success": False})
    
    file = request.files.get('file')
    try:
        stream = io.BytesIO(file.read())
        df = pd.read_excel(stream) if file.filename.endswith(('.xlsx', '.xls')) else pd.read_csv(stream)
        
        # Mapeo de columnas de Elena
        nuevas = {c: est for est, sin in MAPEO_COLUMNAS.items() for c in df.columns if str(c).lower().strip() in sin}
        df.rename(columns=nuevas, inplace=True)
        
        # Guardamos en sesión para RapidFuzz
        session['resumen_datos'] = {
            "columnas": df.columns.tolist(),
            "datos_completos": df.to_dict(orient='records')
        }
        session.modified = True
        return jsonify({"success": True, "mensaje": "Elena ya leyó tu inventario."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email', '').strip().lower()
    with engine.connect() as conn:
        user = conn.execute(text("SELECT email, activo FROM suscripciones WHERE email = :e"), {"e": email}).mappings().fetchone()
    
    if user and user['activo'] == 1:
        session['user'] = user['email']
        return redirect(url_for('index'))
    return render_template('index.html', login_mode=True, error="Usuario no autorizado.")

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)