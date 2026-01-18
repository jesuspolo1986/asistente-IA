from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import pandas as pd
import os
from pyDolarVenezuela.pages import AlCambio
from pyDolarVenezuela import Monitor
from datetime import datetime
from supabase import create_client, Client

app = Flask(__name__)
app.secret_key = 'elena_farmacia_2026_key'

# --- CREDENCIALES SUPABASE ---
SUPABASE_URL = "TU_URL_DE_SUPABASE"
SUPABASE_KEY = "TU_LLAVE_ANON_DE_SUPABASE"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

EXCEL_FILE = 'inventario.xlsx'

def obtener_tasa_real():
    try:
        # Buscamos el valor de AlCambio (el 341.74 que necesitas)
        monitor = Monitor(AlCambio, 'USD')
        monitors_list = monitor.get_all_monitors()
        for m in monitors_list:
            if "BCV" in m.title: return float(m.price)
        return 341.74
    except: return 341.74

@app.route('/')
def index():
    tasa = obtener_tasa_real()
    
    # Intentamos obtener los días de suscripción directamente de la base de datos si el usuario está logueado
    dias_restantes = 10 # Valor por defecto
    if session.get('autenticado') and session.get('fecha_vencimiento'):
        try:
            vence = datetime.strptime(session['fecha_vencimiento'], '%Y-%m-%d')
            dias_restantes = (vence - datetime.now()).days
        except: pass
        
    return render_template('index.html', tasa=tasa, dias_restantes=dias_restantes)

@app.route('/login', methods=['POST'])
def login():
    email_ingresado = request.form.get('email').lower().strip()
    
    try:
        # Consultamos la tabla 'suscripciones'
        # Buscamos por la columna 'email' (asegúrate de que en Supabase se llame así)
        response = supabase.table("suscripciones").select("*").eq("email", email_ingresado).execute()
        
        if len(response.data) > 0:
            usuario_data = response.data[0]
            session['autenticado'] = True
            session['usuario'] = email_ingresado
            
            # Si tienes una columna de vencimiento en Supabase, la guardamos
            if 'fecha_vencimiento' in usuario_data:
                session['fecha_vencimiento'] = usuario_data['fecha_vencimiento']
                
            return redirect(url_for('index'))
        else:
            return "El correo no tiene una suscripción activa.", 401
            
    except Exception as e:
        print(f"Error Supabase: {e}")
        return "Error al conectar con la base de datos de suscripciones.", 500

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/preguntar', methods=['POST'])
def preguntar():
    if not session.get('autenticado'): return jsonify({"respuesta": "Inicia sesión primero."}), 401
    
    data = request.get_json()
    pregunta = data.get('pregunta', '').lower()
    tasa = obtener_tasa_real()
    
    try:
        df = pd.read_excel(EXCEL_FILE)
        match = df[df['Producto'].str.contains(pregunta, case=False, na=False)]
        
        if not match.empty:
            prod = match.iloc[0]['Producto']
            usd = float(match.iloc[0]['Precio_USD'])
            bs = usd * tasa
            return jsonify({
                "respuesta": f"El {prod} cuesta {usd} dólares. Al cambio son {bs:.2f} bolívares.",
                "tasa_sync": tasa
            })
        return jsonify({"respuesta": f"No encontré '{pregunta}'."})
    except:
        return jsonify({"respuesta": "Error al leer el archivo de inventario."}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)