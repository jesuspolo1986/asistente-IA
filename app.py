from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
import pandas as pd
import os
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

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def obtener_tasa_real():
    try:
        monitor = Monitor(AlCambio, 'USD')
        monitores = monitor.get_all_monitors()
        for m in monitores:
            if "BCV" in m.title or "AlCambio" in m.title:
                val = float(m.price)
                # Filtro basado en tu prueba: ignora 341.74 y 0.01
                if 10 < val < 100: 
                    return val
        return 54.20
    except:
        return 54.20

@app.route('/')
def index():
    tasa = obtener_tasa_real()
    dias_restantes = 0
    if session.get('autenticado') and session.get('fecha_vencimiento'):
        try:
            vence = datetime.strptime(session['fecha_vencimiento'], '%Y-%m-%d').date()
            dias_restantes = (vence - datetime.now().date()).days
        except: pass
    return render_template('index.html', tasa=tasa, dias_restantes=dias_restantes)

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email', '').lower().strip()
    try:
        res = supabase.table("suscripciones").select("*").eq("email", email).eq("activo", 1).execute()
        if len(res.data) > 0:
            session['autenticado'] = True
            session['usuario'] = email
            session['fecha_vencimiento'] = str(res.data[0].get('fecha_vencimiento'))
            return redirect(url_for('index'))
        return "Usuario no autorizado o inactivo", 401
    except: return "Error de base de datos", 500

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# --- PANEL ADMINISTRATIVO CON MÉTRICAS ---
@app.route('/admin')
def admin_panel():
    auth = request.args.get('auth_key')
    if auth != ADMIN_PASS: return "No autorizado", 403
    
    res = supabase.table("suscripciones").select("*").execute()
    usuarios = res.data
    hoy = datetime.now().date()
    
    stats = {"activos": 0, "vencidos": 0, "total": len(usuarios)}
    
    for u in usuarios:
        vence = datetime.strptime(u['fecha_vencimiento'], '%Y-%m-%d').date()
        u['vencido'] = vence < hoy
        if u['vencido']:
            stats["vencidos"] += 1
        else:
            stats["activos"] += 1

    return render_template('admin.html', usuarios=usuarios, stats=stats, admin_pass=ADMIN_PASS)

@app.route('/admin/toggle/<int:user_id>')
def toggle_user(user_id):
    auth = request.args.get('auth_key')
    if auth != ADMIN_PASS: return "No autorizado", 403
    res = supabase.table("suscripciones").select("activo").eq("id", user_id).execute()
    nuevo_estado = 0 if res.data[0]['activo'] == 1 else 1
    supabase.table("suscripciones").update({"activo": nuevo_estado}).eq("id", user_id).execute()
    return redirect(url_for('admin_panel', auth_key=ADMIN_PASS))

@app.route('/admin/renovar/<int:user_id>', methods=['POST'])
def renovar_usuario(user_id):
    auth = request.args.get('auth_key')
    if auth != ADMIN_PASS: return "No autorizado", 403
    nueva_fecha = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
    supabase.table("suscripciones").update({"fecha_vencimiento": nueva_fecha, "activo": 1}).eq("id", user_id).execute()
    flash("Renta renovada con éxito", "success")
    return redirect(url_for('admin_panel', auth_key=ADMIN_PASS))

# --- INVENTARIO ---
@app.route('/subir_excel', methods=['POST'])
def subir_excel():
    if 'archivo' not in request.files: return redirect(url_for('index'))
    file = request.files['archivo']
    if file and file.filename.endswith('.xlsx'):
        path = os.path.join(os.getcwd(), EXCEL_FILE)
        file.save(path)
        flash("Inventario actualizado", "success")
    return redirect(url_for('index'))

@app.route('/preguntar', methods=['POST'])
def preguntar():
    data = request.get_json()
    pregunta = data.get('pregunta', '').lower().strip()
    if "activar modo gerencia" in pregunta:
        return jsonify({"respuesta": "Modo gerencia activo.", "modo_admin": True})
    
    tasa = obtener_tasa_real()
    try:
        df = pd.read_excel(EXCEL_FILE, engine='openpyxl')
        match = df[df['Producto'].str.contains(pregunta, case=False, na=False)]
        if not match.empty:
            p, u = match.iloc[0]['Producto'], float(match.iloc[0]['Precio_USD'])
            return jsonify({"respuesta": f"{p}: {u}$. Total: {u*tasa:.2f} Bs."})
    except: pass
    return jsonify({"respuesta": "No encontrado."})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))