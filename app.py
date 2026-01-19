from flask import Flask, render_template, request, jsonify, session, redirect, url_for
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

# Inicialización de Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def obtener_tasa_real():
    """Obtiene la tasa oficial del BCV o la más cercana disponible"""
    try:
        monitor = Monitor(AlCambio, 'USD')
        monitors_list = monitor.get_all_monitors()
        for m in monitors_list:
            nombre = str(getattr(m, 'title', m)).upper()
            if "BCV" in nombre:
                return float(m.price)
        return float(monitors_list[0].price)
    except:
        return 341.74 # Respaldo si falla la conexión

# --- RUTAS DE USUARIO ---

@app.route('/')
def index():
    tasa = obtener_tasa_real()
    dias_restantes = 10
    if session.get('autenticado') and session.get('fecha_vencimiento'):
        try:
            vence = datetime.strptime(session['fecha_vencimiento'], '%Y-%m-%d')
            dias_restantes = (vence.date() - datetime.now().date()).days
        except: pass
    return render_template('index.html', tasa=tasa, dias_restantes=dias_restantes)

@app.route('/login', methods=['POST'])
def login():
    email_ingresado = request.form.get('email', '').lower().strip()
    try:
        res = supabase.table("suscripciones").select("*").eq("email", email_ingresado).eq("activo", 1).execute()
        if len(res.data) > 0:
            session['autenticado'] = True
            session['usuario'] = email_ingresado
            session['fecha_vencimiento'] = str(res.data[0].get('fecha_vencimiento'))
            return redirect(url_for('index'))
        return "Usuario inactivo o no encontrado", 401
    except:
        return "Error de conexión con la base de datos", 500

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# --- RUTAS ADMIN ---

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    auth = request.args.get('auth_key')
    if auth != ADMIN_PASS:
        return "Acceso Denegado", 403

    if request.method == 'POST':
        email = request.form.get('email')
        dias = int(request.form.get('dias'))
        fecha_v = (datetime.now() + timedelta(days=dias)).strftime('%Y-%m-%d')
        try:
            supabase.table("suscripciones").insert({
                "email": email, "fecha_vencimiento": fecha_v, "activo": 1
            }).execute()
        except: pass

    try:
        usuarios = supabase.table("suscripciones").select("*").execute().data
    except:
        usuarios = []
    return render_template('admin.html', usuarios=usuarios, admin_pass=ADMIN_PASS)

@app.route('/subir_excel', methods=['POST'])
def subir_excel():
    auth = request.args.get('auth_key')
    if auth != ADMIN_PASS: return "No autorizado", 403
    file = request.files.get('archivo')
    if file and file.filename.endswith('.xlsx'):
        file.save(EXCEL_FILE)
        return redirect(url_for('admin', auth_key=ADMIN_PASS))
    return "Archivo inválido", 400

@app.route('/preguntar', methods=['POST'])
def preguntar():
    if not session.get('autenticado'): return jsonify({"respuesta": "Inicia sesión."}), 401
    
    data = request.get_json()
    pregunta = data.get('pregunta', '').lower().strip()
    
    # MEJORA: Acceso "Modo Gerencia"
    if "activar modo gerencia" in pregunta:
        return jsonify({
            "respuesta": "Acceso administrativo detectado. Entrando al panel...",
            "redirect": url_for('admin', auth_key=ADMIN_PASS)
        })

    tasa = obtener_tasa_real()
    try:
        if not os.path.exists(EXCEL_FILE):
            return jsonify({"respuesta": "Elena no tiene el inventario.xlsx. Súbelo en el panel admin."})
            
        df = pd.read_excel(EXCEL_FILE)
        match = df[df['Producto'].str.contains(pregunta, case=False, na=False)]
        if not match.empty:
            p, u = match.iloc[0]['Producto'], float(match.iloc[0]['Precio_USD'])
            return jsonify({
                "respuesta": f"El {p} cuesta {u}$. Al cambio son {u*tasa:.2f} bolívares.",
                "tasa_sync": tasa
            })
        return jsonify({"respuesta": f"No encontré '{pregunta}'."})
    except:
        return jsonify({"respuesta": "Error al leer el inventario."})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)