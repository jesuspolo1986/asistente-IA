import os
import io
import requests
import pandas as pd
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from sqlalchemy import create_engine, text
from mistralai import Mistral
from rapidfuzz import process, utils

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "elena_pro_secret_2026")

# --- CONFIGURACIÓN ---
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

# --- FUNCIÓN DE BÚSQUEDA REAL EN INTERNET ---
def obtener_tasa_internet():
    try:
        url = "https://www.bcv.org.ve/"
        headers = {'User-Agent': 'Mozilla/5.0'}
        # verify=False para evitar problemas de certificados en algunos servidores
        response = requests.get(url, headers=headers, verify=False, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extracción específica del valor del dólar en el BCV
        tasa_box = soup.find('div', id='dolar')
        tasa_valor = tasa_box.find('strong').text.strip()
        
        return float(tasa_valor.replace(',', '.'))
    except Exception as e:
        print(f"Error en internet: {e}")
        return None

@app.route('/')
def index():
    if 'user' not in session:
        return render_template('index.html', login_mode=True)
    
    with engine.connect() as conn:
        query = text("SELECT activo, creditos_usados FROM suscripciones WHERE email = :e")
        user_data = conn.execute(query, {"e": session['user']}).mappings().fetchone()
    
    if user_data and user_data['activo'] == 1:
        if 'tasa_actual' not in session:
            session['tasa_actual'] = 36.50
        return render_template('index.html', 
                               login_mode=False, 
                               user=session['user'], 
                               tasa=session['tasa_actual'],
                               creditos_usados=user_data['creditos_usados'] or 0,
                               creditos_totales=500)
    session.clear()
    return render_template('index.html', login_mode=True, error="Suscripción inactiva.")

@app.route('/preguntar', methods=['POST'])
def preguntar():
    if 'user' not in session: return jsonify({"error": "No autorizado"}), 401
    
    data = request.json
    pregunta = data.get("pregunta", "").lower().strip()
    modo_admin = data.get("modo_admin", False)

    # COMANDO: ACTUALIZAR DESDE INTERNET
    if "actualiza la tasa" in pregunta or "busca la tasa" in pregunta:
        nueva = obtener_tasa_internet()
        if nueva:
            v_anterior = session.get('tasa_actual', 0)
            session['tasa_actual'] = nueva
            tendencia = "subió" if nueva > v_anterior else "bajó" if nueva < v_anterior else "se mantiene"
            return jsonify({
                "respuesta": f"He consultado el monitor. La tasa {tendencia} a {nueva} Bolívares.",
                "tasa_sync": nueva
            })
        return jsonify({"respuesta": "No pude conectar con el servidor de la tasa."})

    if pregunta == "activar modo gerencia": return jsonify({"respuesta": "MODO_ADMIN_ACTIVADO"})
    if pregunta in ["activar modo vendedor", "salir de gerencia"]: return jsonify({"respuesta": "MODO_VENDEDOR_ACTIVADO"})

    resumen = session.get('resumen_datos')
    if not resumen: return jsonify({"respuesta": "Elena: Carga un archivo para comenzar."})

    df = pd.DataFrame(resumen['datos_completos'])
    match = process.extractOne(pregunta.replace("precio", "").strip(), df['Producto'].astype(str).tolist(), processor=utils.default_process)
    
    if match and match[1] > 65:
        f = df[df['Producto'] == match[0]].iloc[0]
        tasa = float(session.get('tasa_actual', 36.50))
        p_usd = float(str(f['Precio Venta']).replace('$', '').replace(',', ''))
        
        if modo_admin:
            costo = float(str(f.get('Costo', 0)).replace('$', '').replace(',', ''))
            m = ((p_usd - costo) / p_usd) * 100 if p_usd > 0 else 0
            res = f"📊 {match[0]} | Costo: ${costo:,.2f} | Venta: ${p_usd:,.2f} | Margen: {m:.1f}% | Stock: {int(f.get('Stock Actual', 0))}"
        else:
            res = f"El {match[0]} cuesta {p_usd * tasa:,.2f} Bs ({p_usd:,.2f} USD)."
        
        return jsonify({"respuesta": res, "tasa_sync": tasa})

    return responder_con_ia(pregunta, resumen)

def responder_con_ia(pregunta, resumen):
    prompt = f"Eres Elena, asistente de farmacia. Inventario: {resumen['columnas']}. Responde breve."
    response = client.chat.complete(model="mistral-small", messages=[{"role": "system", "content": prompt}, {"role": "user", "content": pregunta}])
    return jsonify({"respuesta": response.choices[0].message.content})

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files.get('file')
    try:
        df = pd.read_excel(io.BytesIO(file.read())) if file.filename.endswith(('.xlsx', '.xls')) else pd.read_csv(io.BytesIO(file.read()))
        nuevas = {c: est for est, sin in MAPEO_COLUMNAS.items() for c in df.columns if str(c).lower().strip() in sin}
        df.rename(columns=nuevas, inplace=True)
        session['resumen_datos'] = {"columnas": df.columns.tolist(), "datos_completos": df.to_dict(orient='records')}
        session.modified = True
        return jsonify({"success": True, "mensaje": "Inventario leído."})
    except Exception as e: return jsonify({"success": False, "error": str(e)})

@app.route('/login', methods=['POST'])
def login():
    session['user'] = request.form.get('email', '').strip().lower()
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)