from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
import pandas as pd
import os
import io
from pyDolarVenezuela.pages import AlCambio
from pyDolarVenezuela import Monitor
from datetime import datetime, timedelta
from supabase import create_client, Client

app = Flask(__name__)
app.secret_key = 'elena_farmacia_2026_key'

# --- CONFIGURACIÓN ---
SUPABASE_URL = "https://kebpamfydhnxeaeegulx.supabase.co"
SUPABASE_KEY = "sb_secret_lSrahuG5Nv32T1ZaV7lfRw_WFXuiP4H"
ADMIN_PASS = "1234"
EXCEL_FILE = 'inventario.xlsx'

inventario_memoria = {"df": None, "tasa": 54.20}

# Mapeo según tu CSV: "Precio Venta" -> Precio_USD
MAPEO_COLUMNAS = {
    'Producto': ['producto', 'descripcion', 'nombre', 'articulo', 'item'],
    'Precio_USD': ['precio venta', 'pvp', 'precio', 'venta', 'precio_unitario', 'precio_usd', 'costo_usd'],
    'Stock': ['stock actual', 'stock', 'cantidad', 'existencia']
}

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def obtener_tasa_real():
    try:
        monitor = Monitor(AlCambio, 'USD')
        monitores = monitor.get_all_monitors()
        for m in monitores:
            if "BCV" in m.title:
                val = float(m.price)
                if 10 < val < 100: return val
        return 54.20
    except: return 54.20

@app.route('/')
def index():
    if "tasa_manual" not in inventario_memoria:
        inventario_memoria["tasa"] = obtener_tasa_real()
    
    tasa = inventario_memoria["tasa"]
    dias_restantes = 1
    if session.get('autenticado') and session.get('fecha_vencimiento'):
        try:
            vence = datetime.strptime(session['fecha_vencimiento'], '%Y-%m-%d').date()
            dias_restantes = (vence - datetime.now().date()).days
        except: pass
    return render_template('index.html', tasa=tasa, dias_restantes=dias_restantes)

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files.get('archivo')
    if not file: return jsonify({"success": False, "mensaje": "Sin archivo"})
    try:
        stream = io.BytesIO(file.read())
        if file.filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(stream, engine='openpyxl')
        else:
            df = pd.read_csv(stream)
        
        nuevas = {c: est for est, sin in MAPEO_COLUMNAS.items() for c in df.columns if str(c).lower().strip() in sin}
        df.rename(columns=nuevas, inplace=True)
        df.columns = [str(c).strip() for c in df.columns]
        
        inventario_memoria["df"] = df
        stream.seek(0)
        with open(EXCEL_FILE, "wb") as f: f.write(stream.getbuffer())
        return jsonify({"success": True, "mensaje": "Inventario cargado"})
    except Exception as e: return jsonify({"success": False, "error": str(e)})

@app.route('/preguntar', methods=['POST'])
def preguntar():
    data = request.get_json()
    
    # Cambio de tasa manual
    if data.get('nueva_tasa'):
        try:
            inventario_memoria["tasa"] = float(data.get('nueva_tasa'))
            inventario_memoria["tasa_manual"] = True
            return jsonify({"respuesta": "Tasa actualizada", "tasa": inventario_memoria["tasa"]})
        except: return jsonify({"respuesta": "Error en tasa"})

    raw_pregunta = data.get('pregunta', '').lower().strip()
    if "activar modo gerencia" in raw_pregunta:
        return jsonify({"respuesta": "Modo gerencia activo.", "modo_admin": True})

    # Limpieza de lenguaje natural
    palabras_sobrantes = ["cuanto", "cuesta", "vale", "precio", "de", "del", "el", "la", "tiene", "cual", "es", "busco"]
    query_limpio = raw_pregunta
    for palabra in palabras_sobrantes:
        query_limpio = query_limpio.replace(f" {palabra} ", " ").replace(f"{palabra} ", "")

    tasa = inventario_memoria["tasa"]
    
    try:
        df = inventario_memoria["df"]
        if df is None:
            if os.path.exists(EXCEL_FILE):
                df = pd.read_excel(EXCEL_FILE, engine='openpyxl') if EXCEL_FILE.endswith('.xlsx') else pd.read_csv(EXCEL_FILE)
                inventario_memoria["df"] = df
            else: return jsonify({"respuesta": "Elena no tiene datos. Sube el inventario."})

        # Búsqueda múltiple
        matches = df[df['Producto'].str.contains(query_limpio, case=False, na=False)]
        
        if matches.empty:
            return jsonify({"respuesta": f"No encontré nada relacionado con {query_limpio}."})

        if len(matches) == 1:
            p = matches.iloc[0]['Producto']
            u = float(matches.iloc[0]['Precio_USD'])
            s = matches.iloc[0]['Stock'] if 'Stock' in matches.columns else "?"
            total_bs = round(u * tasa, 2)
            return jsonify({"respuesta": f"El {p} tiene un precio de {u} dólares, que son {total_bs} bolívares. Quedan {s} unidades."})
        
        elif len(matches) > 5:
            return jsonify({"respuesta": f"Encontré {len(matches)} productos similares a '{query_limpio}'. ¿Podrías ser más específico?"})

        else:
            opciones = []
            for i, row in matches.iterrows():
                nom = row['Producto']
                pre = row['Precio_USD']
                bs = round(float(pre) * tasa, 2)
                opciones.append(f"{nom} en {pre}$ ({bs} Bs)")
            
            texto_opciones = " . también tengo . ".join(opciones)
            return jsonify({"respuesta": f"Tengo varias presentaciones: {texto_opciones}. ¿Cuál buscabas?"})

    except Exception as e:
        return jsonify({"respuesta": f"Error: {str(e)}"})

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email', '').lower().strip()
    res = supabase.table("suscripciones").select("*").eq("email", email).eq("activo", 1).execute()
    if res.data:
        session['autenticado'] = True
        session['usuario'] = email
        session['fecha_vencimiento'] = res.data[0]['fecha_vencimiento']
        return redirect(url_for('index'))
    return "No autorizado", 401

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))