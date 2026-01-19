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

# Diccionario para mantener los datos en RAM (como en tu proyecto de prueba)
inventario_memoria = {"df": None, "tasa": 54.20}

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
    except:
        return 54.20

@app.route('/')
def index():
    tasa = obtener_tasa_real()
    inventario_memoria["tasa"] = tasa
    dias_restantes = 1
    if session.get('autenticado') and session.get('fecha_vencimiento'):
        try:
            vence = datetime.strptime(session['fecha_vencimiento'], '%Y-%m-%d').date()
            dias_restantes = (vence - datetime.now().date()).days
        except: pass
    return render_template('index.html', tasa=tasa, dias_restantes=dias_restantes)

# --- CARGA DE EXCEL (LOGICA MEJORADA) ---
@app.route('/subir_excel', methods=['POST'])
def subir_excel():
    # Buscamos el nombre 'archivo' que es el que tiene tu HTML
    file = request.files.get('archivo')
    if not file:
        flash("No se seleccionó ningún archivo", "danger")
        return redirect(url_for('index'))
    
    try:
        # LEER EN MEMORIA (Igual que el proyecto que te funciona)
        stream = io.BytesIO(file.read())
        df = pd.read_excel(stream, engine='openpyxl')
        
        # Limpiar nombres de columnas por si acaso
        df.columns = [str(c).strip() for c in df.columns]
        
        # Guardar en RAM para respuesta inmediata
        inventario_memoria["df"] = df
        
        # Guardar en DISCO para persistencia
        stream.seek(0)
        with open(EXCEL_FILE, "wb") as f:
            f.write(stream.getbuffer())
            
        flash("¡Inventario cargado exitosamente en memoria!", "success")
    except Exception as e:
        flash(f"Error al procesar Excel: {str(e)}", "danger")
    
    return redirect(url_for('index'))

@app.route('/preguntar', methods=['POST'])
def preguntar():
    data = request.get_json()
    pregunta = data.get('pregunta', '').lower().strip()
    
    if "activar modo gerencia" in pregunta:
        return jsonify({"respuesta": "Modo gerencia activo.", "modo_admin": True})

    tasa = inventario_memoria["tasa"]
    
    try:
        # 1. Intentar usar la RAM
        df = inventario_memoria["df"]
        
        # 2. Si la RAM está vacía, intentar leer el archivo guardado
        if df is None:
            if os.path.exists(EXCEL_FILE):
                df = pd.read_excel(EXCEL_FILE, engine='openpyxl')
                inventario_memoria["df"] = df
            else:
                return jsonify({"respuesta": "Elena no tiene datos. Sube el Excel primero."})

        # Búsqueda (ajustada a tus columnas: Producto y Precio_USD)
        match = df[df['Producto'].str.contains(pregunta, case=False, na=False)]
        
        if not match.empty:
            p = match.iloc[0]['Producto']
            u = float(match.iloc[0]['Precio_USD'])
            return jsonify({"respuesta": f"{p}: {u}$. Total: {u*tasa:.2f} Bs."})
        
        return jsonify({"respuesta": f"No encontré '{pregunta}'."})
    except Exception as e:
        return jsonify({"respuesta": f"Error en la consulta: {str(e)}"})

# --- RUTAS DE LOGIN / LOGOUT / ADMIN ---
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
    app.run(host='0.0.0.0', port=8000)