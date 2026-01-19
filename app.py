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

MAPEO_COLUMNAS = {
    'Producto': ['producto', 'descripcion', 'nombre', 'articulo', 'item'],
    'Precio_USD': ['precio venta', 'pvp', 'precio', 'venta', 'precio_unitario', 'precio_usd', 'costo_usd']
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
        df = pd.read_excel(stream, engine='openpyxl') if file.filename.endswith(('.xlsx', '.xls')) else pd.read_csv(stream)
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
    
    if data.get('nueva_tasa'):
        try:
            inventario_memoria["tasa"] = float(data.get('nueva_tasa'))
            inventario_memoria["tasa_manual"] = True
            return jsonify({"respuesta": "Tasa actualizada", "tasa": inventario_memoria["tasa"]})
        except: return jsonify({"respuesta": "Error en tasa"})

    raw_pregunta = data.get('pregunta', '').lower().strip()
    if "activar modo gerencia" in raw_pregunta:
        return jsonify({"respuesta": "Modo gerencia activo.", "modo_admin": True})

    palabras_sobrantes = ["cuanto", "cuesta", "vale", "precio", "de", "del", "el", "la", "tiene", "cual", "es"]
    query_limpio = raw_pregunta
    for palabra in palabras_sobrantes:
        query_limpio = query_limpio.replace(f" {palabra} ", " ").replace(f"{palabra} ", "")

    tasa = inventario_memoria["tasa"]
    
    try:
        df = inventario_memoria["df"]
        if df is None:
            if os.path.exists(EXCEL_FILE):
                df = pd.read_excel(EXCEL_FILE, engine='openpyxl')
                inventario_memoria["df"] = df
            else: return jsonify({"respuesta": "Sube el inventario primero."})

        # Búsqueda de múltiples coincidencias
        matches = df[df['Producto'].str.contains(query_limpio, case=False, na=False)]
        
        if matches.empty:
            return jsonify({"respuesta": f"No encontré {query_limpio}."})

        if len(matches) == 1:
            p = matches.iloc[0]['Producto']
            u = float(matches.iloc[0]['Precio_USD'])
            total_bs = round(u * tasa, 2)
            return jsonify({"respuesta": f"El {p} tiene un precio de {u} dólares, que son {total_bs} bolívares."})
        
        else:
            # Si hay varios, enumerar los primeros 3 para no cansar al usuario
            opciones = []
            for i, row in matches.head(3).iterrows():
                nom = row['Producto']
                pre = row['Precio_USD']
                bs = round(float(pre) * tasa, 2)
                opciones.append(f"{nom} en {pre}$ ({bs} Bs)")
            
            texto_opciones = " . también tengo . ".join(opciones)
            return jsonify({"respuesta": f"Encontré varias opciones: {texto_opciones}. ¿Cuál necesitas?"})

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

@app.route('/admin')
def admin_panel():
    auth = request.args.get('auth_key')
    if auth != ADMIN_PASS: return "Acceso Denegado", 403
    res = supabase.table("suscripciones").select("*").execute()
    usuarios = res.data
    hoy = datetime.now().date()
    stats = {"activos": 0, "vencidos": 0, "total": len(usuarios)}
    for u in usuarios:
        vence = datetime.strptime(u['fecha_vencimiento'], '%Y-%m-%d').date()
        u['vencido'] = vence < hoy
        if u['vencido']: stats["vencidos"] += 1
        else: stats["activos"] += 1
    return render_template('admin.html', usuarios=usuarios, stats=stats, admin_pass=ADMIN_PASS)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))