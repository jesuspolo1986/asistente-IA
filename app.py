from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import pandas as pd
import os
from pyDolarVenezuela.pages import AlCambio
from pyDolarVenezuela import Monitor
from datetime import datetime
from supabase import create_client, Client

app = Flask(__name__)
app.secret_key = 'elena_farmacia_2026_key'

# --- CREDENCIALES SUPABASE (CORREGIDAS) ---
# --- CREDENCIALES SUPABASE ---
SUPABASE_URL = "https://kebpamfydhnxeaeegulx.supabase.co"

# Pega aquí la clave que me acabas de pasar
SUPABASE_KEY = "sb_secret_lSrahuG5Nv32T1ZaV7lfRw_WFXuiP4H" 



# Inicialización segura
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"Error inicializando Supabase: {e}")

EXCEL_FILE = 'inventario.xlsx'

def obtener_tasa_real():
    try:
        # Monitor AlCambio para obtener el 341.74 o valor actual
        monitor = Monitor(AlCambio, 'USD')
        monitors_list = monitor.get_all_monitors()
        for m in monitors_list:
            if "BCV" in m.title: return float(m.price)
        return 341.74
    except:
        return 341.74

@app.route('/')
def index():
    tasa = obtener_tasa_real()
    
    # Lógica de días de suscripción
    dias_restantes = 10 # Valor base
    if session.get('autenticado') and session.get('fecha_vencimiento'):
        try:
            vence = datetime.strptime(session['fecha_vencimiento'], '%Y-%m-%d')
            dias_restantes = (vence - datetime.now()).days
        except: pass
        
    return render_template('index.html', tasa=tasa, dias_restantes=dias_restantes)

@app.route('/login', methods=['POST'])
def login():
    email_ingresado = request.form.get('email', '').lower().strip()
    
    try:
        # Consulta a la tabla 'suscripciones'
        # Nota: Asegúrate de que la columna en Supabase se llame 'email'
        response = supabase.table("suscripciones").select("*").eq("email", email_ingresado).execute()
        
        if len(response.data) > 0:
            usuario_data = response.data[0]
            session['autenticado'] = True
            session['usuario'] = email_ingresado
            
            # Guardamos la fecha si existe para el banner de Elena
            if 'fecha_vencimiento' in usuario_data:
                session['fecha_vencimiento'] = str(usuario_data['fecha_vencimiento'])
                
            return redirect(url_for('index'))
        else:
            return "El correo no está registrado en el sistema de suscripciones.", 401
            
    except Exception as e:
        print(f"Error en Login Supabase: {e}")
        return "Error técnico al validar suscripción.", 500

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/preguntar', methods=['POST'])
def preguntar():
    if not session.get('autenticado'): 
        return jsonify({"respuesta": "Acceso denegado. Por favor inicia sesión."}), 401
    
    data = request.get_json()
    pregunta = data.get('pregunta', '').lower()
    tasa = obtener_tasa_real()
    
    try:
        if not os.path.exists(EXCEL_FILE):
            return jsonify({"respuesta": "Elena no encuentra el archivo de inventario.xlsx."})

        df = pd.read_excel(EXCEL_FILE)
        # Búsqueda por nombre de producto en la columna 'Producto'
        match = df[df['Producto'].str.contains(pregunta, case=False, na=False)]
        
        if not match.empty:
            prod = match.iloc[0]['Producto']
            usd = float(match.iloc[0]['Precio_USD'])
            bs = usd * tasa
            return jsonify({
                "respuesta": f"El {prod} tiene un costo de {usd} dólares. A tasa de {tasa}, serían {bs:.2f} bolívares.",
                "tasa_sync": tasa
            })
        return jsonify({"respuesta": f"Lo siento, no tengo '{pregunta}' en el inventario actual."})
    except Exception as e:
        return jsonify({"respuesta": "Error al leer los datos del inventario."}), 500

if __name__ == '__main__':
    # Configuración de puerto para Koyeb
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)