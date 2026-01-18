import os
import io
import requests
import pandas as pd
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from sqlalchemy import create_engine, text
from mistralai import Mistral
from rapidfuzz import process, utils
import urllib3

# Desactivar advertencias de certificados para el BCV
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "elena_pro_secure_2026")

# --- CONFIGURACIÓN DE BASE DE DATOS ---
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:aSxRZ3rVrMu2Oasu@db.kebpamfydhnxeaeegulx.supabase.co:6543/postgres")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
client = Mistral(api_key=os.environ.get("MISTRAL_API_KEY", "p2KCokd08zRypMAZQxMbC4ImxkM5DPK1"))

# Mapeo inteligente de columnas para el Excel
MAPEO_COLUMNAS = {
    'Producto': ['producto', 'descripcion', 'nombre', 'articulo', 'item'],
    'Precio Venta': ['precio venta', 'pvp', 'precio', 'venta', 'precio_unitario'],
    'Costo': ['costo', 'compra', 'p.costo'],
    'Stock Actual': ['stock actual', 'stock', 'cantidad', 'existencia']
}

def obtener_tasa_real():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    # Intento 1: BCV Oficial
    try:
        res = requests.get("https://www.bcv.org.ve/", headers=headers, verify=False, timeout=8)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            valor = soup.find('div', id='dolar').find('strong').text.strip()
            return float(valor.replace(',', '.'))
    except:
        pass
    
    # Intento 2: API de Respaldo (Si el BCV bloquea el servidor)
    try:
        res = requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=5)
        return float(res.json()['rates']['VES'])
    except:
        return None

@app.route('/')
def index():
    if 'user' not in session:
        return render_template('index.html', login_mode=True)
    
    # Actualización automática al entrar a la app
    tasa_fresca = obtener_tasa_real()
    if tasa_fresca:
        session['tasa_actual'] = tasa_fresca
    elif 'tasa_actual' not in session:
        session['tasa_actual'] = 344.51 # Valor base de seguridad

    return render_template('index.html', 
                           login_mode=False, 
                           user=session['user'], 
                           tasa=session.get('tasa_actual'))

@app.route('/preguntar', methods=['POST'])
def preguntar():
    if 'user' not in session: return jsonify({"error": "No autorizado"}), 401
    
    data = request.json
    pregunta = data.get("pregunta", "").lower().strip()
    modo_admin = data.get("modo_admin", False)

    # COMANDO DE TASA (Manual o por voz)
    if "actualiza la tasa" in pregunta or "busca la tasa" in pregunta:
        v_anterior = session.get('tasa_actual', 0)
        nueva = obtener_tasa_real()
        if nueva:
            session['tasa_actual'] = nueva
            tendencia = "subió" if nueva > v_anterior else "bajó" if nueva < v_anterior else "se mantiene"
            return jsonify({
                "respuesta": f"He verificado el monitor. La tasa {tendencia} a {nueva:,.2f} Bolívares.",
                "tasa_sync": nueva
            })
        return jsonify({"respuesta": "No pude conectar con el servidor de la tasa."})

    # CONTROL DE MODOS
    if pregunta == "activar modo gerencia": return jsonify({"respuesta": "MODO_ADMIN_ACTIVADO"})
    if pregunta in ["activar modo vendedor", "salir de gerencia"]: return jsonify({"respuesta": "MODO_VENDEDOR_ACTIVADO"})

    resumen = session.get('resumen_datos')
    if not resumen: return jsonify({"respuesta": "Elena: Por favor, carga el inventario en herramientas."})

    # BÚSQUEDA DE PRODUCTOS
    df = pd.DataFrame(resumen['datos_completos'])
    match = process.extractOne(pregunta.replace("precio", "").strip(), df['Producto'].astype(str).tolist(), processor=utils.default_process)
    
    if match and match[1] > 65:
        f = df[df['Producto'] == match[0]].iloc[0]
        tasa = float(session.get('tasa_actual', 344.51))
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
    prompt = f"Eres Elena, asistente de farmacia. Datos: {resumen['columnas']}. Responde breve."
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
        return jsonify({"success": True, "mensaje": "Inventario cargado exitosamente."})
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