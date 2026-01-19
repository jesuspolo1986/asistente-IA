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
        monitors_list = monitor.get_all_monitors()
        for m in monitors_list:
            nombre = str(getattr(m, 'title', m)).upper()
            if "BCV" in nombre:
                return float(m.price)
        return float(monitors_list[0].price)
    except:
        return 341.74

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
    email = request.form.get('email', '').lower().strip()
    try:
        res = supabase.table("suscripciones").select("*").eq("email", email).eq("activo", 1).execute()
        if len(res.data) > 0:
            session['autenticado'] = True
            session['usuario'] = email
            session['fecha_vencimiento'] = str(res.data[0].get('fecha_vencimiento'))
            return redirect(url_for('index'))
        return "Usuario no autorizado", 401
    except: return "Error de base de datos", 500

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/subir_excel', methods=['POST'])
def subir_excel():
    file = request.files.get('archivo')
    if file and file.filename.endswith('.xlsx'):
        file.save(EXCEL_FILE)
        # Usamos flash para la confirmación visual
        flash("¡Inventario actualizado con éxito!", "success")
        return redirect(url_for('index'))
    return "Error en archivo", 400

@app.route('/preguntar', methods=['POST'])
def preguntar():
    if not session.get('autenticado'): return jsonify({"respuesta": "Inicia sesión."}), 401
    data = request.get_json()
    pregunta = data.get('pregunta', '').lower().strip()
    
    if "activar modo gerencia" in pregunta:
        return jsonify({"respuesta": "Modo gerencia activado. Panel de carga disponible.", "modo_admin": True})

    tasa = obtener_tasa_real()
    try:
        if not os.path.exists(EXCEL_FILE):
            return jsonify({"respuesta": "Elena no tiene el inventario. Súbelo en modo gerencia."})
        df = pd.read_excel(EXCEL_FILE)
        match = df[df['Producto'].str.contains(pregunta, case=False, na=False)]
        if not match.empty:
            p, u = match.iloc[0]['Producto'], float(match.iloc[0]['Precio_USD'])
            return jsonify({"respuesta": f"El {p} cuesta {u}$. Son {u*tasa:.2f} Bs."})
        return jsonify({"respuesta": f"No encontré {pregunta}."})
    except: return jsonify({"respuesta": "Error al leer inventario."})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))