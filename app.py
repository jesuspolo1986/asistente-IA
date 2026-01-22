from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
import pandas as pd
import os
import io
from pyDolarVenezuela.pages import AlCambio
from pyDolarVenezuela import Monitor
from datetime import datetime
from supabase import create_client, Client
import time
from rapidfuzz import process, utils

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
    'Precio_USD': ['precio venta', 'pvp', 'precio', 'venta', 'precio_unitario', 'precio_usd', 'costo_usd'],
    'Stock': ['stock actual', 'stock', 'cantidad', 'existencia']
}

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- FUNCIONES DE APOYO ---
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

# --- RUTAS DE AUTENTICACIÓN ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').lower().strip()
        password = request.form.get('password')
        
        res = supabase.table("suscripciones").select("*").eq("email", email).eq("activo", 1).execute()
        
        if res.data:
            user = res.data[0]
            if user.get('password') == password:
                session['logged_in'] = True
                session['usuario'] = email
                session['fecha_vencimiento'] = user['fecha_vencimiento']
                return redirect(url_for('index'))
            else:
                return render_template('login.html', error="Clave incorrecta")
        return render_template('login.html', error="Usuario no activo o no registrado")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- RUTA PRINCIPAL (ELENA CHAT) ---
@app.route('/')
def index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    if "tasa_manual" not in inventario_memoria:
        inventario_memoria["tasa"] = obtener_tasa_real()
    
    tasa = inventario_memoria["tasa"]
    dias_restantes = 0
    if session.get('fecha_vencimiento'):
        try:
            vence = datetime.strptime(session['fecha_vencimiento'], '%Y-%m-%d').date()
            dias_restantes = (vence - datetime.now().date()).days
        except: pass
        
    return render_template('index.html', tasa=tasa, dias_restantes=dias_restantes, email=session.get('usuario'))

# --- RUTAS DE NEGOCIO (ELENA LOGIC) ---
@app.route('/preguntar', methods=['POST'])
def preguntar():
    t_inicio = time.time()
    data = request.get_json()
    usuario_email = session.get('usuario', 'anonimo@farmacia.com')
    ip_cliente = request.headers.get('X-Forwarded-For', request.remote_addr)

    if data.get('nueva_tasa'):
        try:
            inventario_memoria["tasa"] = float(data.get('nueva_tasa'))
            inventario_memoria["tasa_manual"] = True
            return jsonify({"respuesta": "Tasa actualizada", "tasa": inventario_memoria["tasa"]})
        except: return jsonify({"respuesta": "Error en tasa"})

    pregunta_raw = data.get('pregunta', '').lower().strip()
    
    if "activar modo gerencia" in pregunta_raw:
        return jsonify({"respuesta": "Modo gerencia activo.", "modo_admin": True})

    df = inventario_memoria["df"]
    if df is None:
        if os.path.exists(EXCEL_FILE):
            df = pd.read_excel(EXCEL_FILE, engine='openpyxl') if EXCEL_FILE.endswith('.xlsx') else pd.read_csv(EXCEL_FILE)
            inventario_memoria["df"] = df
        else:
            return jsonify({"respuesta": "Elena no tiene datos. Sube el inventario en Gerencia."})

    tasa = inventario_memoria["tasa"]
    busqueda_exitosa = False
    
    try:
        # Búsqueda Difusa
        resultados = process.extract(pregunta_raw, df['Producto'].astype(str).tolist(), limit=3)
        matches_validos = [r for r in resultados if r[1] > 60]

        if not matches_validos:
            respuesta_final = f"No encontré ese producto."
        else:
            nombre_match = matches_validos[0][0]
            fila = df[df['Producto'] == nombre_match].iloc[0]
            p_usd = float(fila['Precio_USD'])
            p_bs = p_usd * tasa
            stock = fila.get('Stock', '?')
            respuesta_final = f"El {nombre_match} cuesta {p_usd:,.2f} $ ({p_bs:,.2f} Bs). Stock: {stock}"
            busqueda_exitosa = True
    except Exception as e:
        respuesta_final = f"Error: {str(e)}"

    # Registro en Supabase
    try:
        supabase.table("logs_actividad").insert({
            "email": usuario_email,
            "accion": "CONSULTA",
            "detalle": pregunta_raw,
            "ip_address": ip_cliente,
            "exito": busqueda_exitosa
        }).execute()
    except: pass

    return jsonify({"respuesta": respuesta_final})

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files.get('archivo')
    if not file: return jsonify({"success": False})
    try:
        stream = io.BytesIO(file.read())
        df = pd.read_excel(stream) if file.filename.endswith('.xlsx') else pd.read_csv(stream)
        nuevas = {c: est for est, sin in MAPEO_COLUMNAS.items() for c in df.columns if str(c).lower().strip() in sin}
        df.rename(columns=nuevas, inplace=True)
        inventario_memoria["df"] = df
        return jsonify({"success": True})
    except Exception as e: return jsonify({"success": False, "error": str(e)})

# --- RUTAS ADMINISTRATIVAS ---
@app.route('/admin')
def admin_panel():
    auth = request.args.get('auth_key')
    if auth != ADMIN_PASS: return "No autorizado", 403
    
    from collections import Counter
    try:
        usuarios = supabase.table("suscripciones").select("*").execute().data
        logs = supabase.table("logs_actividad").select("*").order("fecha", desc=True).limit(50).execute().data
        
        # Procesar ranking
        emails = [l['email'] for l in logs if l['email']]
        conteo = Counter(emails)
        ranking = [{"email": e, "count": c, "salud": 100} for e, c in conteo.most_common(5)]
        
        stats = {"total": len(usuarios), "activos": len([u for u in usuarios if u['activo'] == 1]), "vencidos": 0}
        return render_template('admin.html', usuarios=usuarios, stats=stats, logs=logs, ranking=ranking, admin_pass=ADMIN_PASS)
    except Exception as e: return f"Error Admin: {e}", 500

@app.route('/admin/crear', methods=['POST'])
def crear_usuario():
    auth = request.form.get('auth_key')
    if auth != ADMIN_PASS: return "Error", 403
    data = {
        "email": request.form.get('email').lower(),
        "password": request.form.get('password'),
        "fecha_vencimiento": request.form.get('vence'),
        "activo": 1
    }
    supabase.table("suscripciones").insert(data).execute()
    return redirect(url_for('admin_panel', auth_key=ADMIN_PASS))

@app.route('/admin/eliminar', methods=['POST'])
def eliminar_usuario():
    if request.form.get('auth_key') != ADMIN_PASS: return "Error", 403
    supabase.table("suscripciones").delete().eq("email", request.form.get('email')).execute()
    return redirect(url_for('admin_panel', auth_key=ADMIN_PASS))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))