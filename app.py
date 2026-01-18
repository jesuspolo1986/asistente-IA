import os
import io
import pandas as pd
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, send_file
from sqlalchemy import create_engine, text
from mistralai import Mistral
from rapidfuzz import process, utils
from datetime import datetime

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
    
    with engine.connect() as conn:
        query = text("SELECT fecha_vencimiento, activo, creditos_usados FROM suscripciones WHERE email = :e")
        user_data = conn.execute(query, {"e": session['user']}).mappings().fetchone()
    
    if user_data and user_data['activo'] == 1:
        tasa = session.get('tasa_actual', 36.50)
        # Importante: Usamos index.html porque ahora es el archivo unificado
        return render_template('index.html', 
                               login_mode=False, 
                               user=session['user'], 
                               tasa=tasa,
                               creditos_usados=user_data['creditos_usados'] or 0,
                               creditos_totales=500) # Ajusta según tu plan
    
    session.clear()
    return render_template('index.html', login_mode=True, error="Suscripción inactiva o vencida.")

# --- LÓGICA DE ELENA ---

@app.route('/preguntar', methods=['POST'])
def preguntar():
    if 'user' not in session: return jsonify({"error": "No autorizado"}), 401
    
    data = request.json
    pregunta = data.get("pregunta", "").lower().strip()
    modo_admin = data.get("modo_admin", False)
    
    # COMANDO SECRETO PARA ACTIVAR MODO GERENCIA
    if pregunta == "activar modo gerencia":
        return jsonify({"respuesta": "MODO_ADMIN_ACTIVADO"})

    # ACTUALIZACIÓN DE TASA (SÓLO ADMIN)
    if data.get("nueva_tasa") and modo_admin:
        try:
            session['tasa_actual'] = float(data.get("nueva_tasa"))
            return jsonify({"respuesta": f"Tasa actualizada a {session['tasa_actual']}", "tasa_sync": session['tasa_actual']})
        except: pass

    resumen = session.get('resumen_datos')
    if not resumen:
        return jsonify({"respuesta": "Elena: Hola, por favor carga el inventario en el botón de herramientas para poder ayudarte."})

    # 1. Búsqueda con RapidFuzz
    df = pd.DataFrame(resumen['datos_completos'])
    lista_productos = df['Producto'].astype(str).tolist()
    match = process.extractOne(pregunta.replace("precio", "").strip(), lista_productos, processor=utils.default_process)
    
    if match and match[1] > 65:
        f = df[df['Producto'] == match[0]].iloc[0]
        tasa = session.get('tasa_actual', 36.50)
        p_usd = float(f['Precio Venta'])
        p_bs = p_usd * tasa
        
        if modo_admin:
            # Blindado: Datos de costo solo en modo admin
            costo = float(f.get('Costo', 0))
            m = ((p_usd - costo) / p_usd) * 100 if p_usd > 0 else 0
            res = f"📊 {match[0]} | Costo: ${costo:.2f} | Venta: ${p_usd:.2f} | Margen: {m:.1f}% | Stock: {int(f.get('Stock Actual', 0))}"
        else:
            res = f"El {match[0]} tiene un costo de {p_bs:,.2f} Bolívares (o {p_usd:,.2f} Dólares)."
        
        actualizar_creditos(session['user'])
        return jsonify({"respuesta": res, "tasa_sync": tasa})

    # 2. IA para preguntas generales
    return responder_con_ia(pregunta, resumen)

def actualizar_creditos(email):
    with engine.begin() as conn:
        conn.execute(text("UPDATE suscripciones SET creditos_usados = COALESCE(creditos_usados, 0) + 1 WHERE email = :e"), {"e": email})

def responder_con_ia(pregunta, resumen):
    # Prompt optimizado para Elena
    prompt = f"Eres Elena, una asistente de farmacia experta. Tienes estos datos de inventario: {resumen['columnas']}. Responde de forma amable y profesional."
    response = client.chat.complete(model="mistral-small", messages=[{"role": "system", "content": prompt}, {"role": "user", "content": pregunta}])
    return jsonify({"respuesta": response.choices[0].message.content})

# --- CARGA DE ARCHIVOS ---

@app.route('/upload', methods=['POST'])
def upload():
    if 'user' not in session: return jsonify({"success": False})
    
    file = request.files.get('file')
    if not file: return jsonify({"success": False, "mensaje": "No se seleccionó ningún archivo."})
    
    try:
        stream = io.BytesIO(file.read())
        df = pd.read_excel(stream) if file.filename.endswith(('.xlsx', '.xls')) else pd.read_csv(stream)
        
        # Mapeo de columnas automático
        nuevas = {c: est for est, sin in MAPEO_COLUMNAS.items() for c in df.columns if str(c).lower().strip() in sin}
        df.rename(columns=nuevas, inplace=True)
        
        # Asegurar que existan las columnas mínimas
        for col in MAPEO_COLUMNAS.keys():
            if col not in df.columns: df[col] = 0

        session['resumen_datos'] = {
            "columnas": df.columns.tolist(),
            "datos_completos": df.to_dict(orient='records')
        }
        session.modified = True
        return jsonify({"success": True, "mensaje": "¡Inventario cargado! Ya puedes consultar precios."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email', '').strip().lower()
    with engine.connect() as conn:
        user = conn.execute(text("SELECT email, activo FROM suscripciones WHERE email = :e"), {"e": email}).mappings().fetchone()
    
    if user and user['activo'] == 1:
        session['user'] = user['email']
        session['tasa_actual'] = 36.50 # Tasa inicial
        return redirect(url_for('index'))
    return render_template('index.html', login_mode=True, error="Acceso denegado. Contacte a soporte.")

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)