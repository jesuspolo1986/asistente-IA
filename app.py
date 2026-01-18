from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import pandas as pd
import os
from pyDolarVenezuela.pages import AlCambio
from pyDolarVenezuela import Monitor
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'elena_farmacia_2026_key'

# --- CONFIGURACIÓN ---
EXCEL_FILE = 'inventario.xlsx'
# Lista de correos autorizados (puedes añadir más aquí)
CORREOS_AUTORIZADOS = ["farmacia@admin.com", "vendedor1@farmacia.com", "elena@farmacia.com"]
FECHA_VENCIMIENTO = datetime(2026, 1, 19) 

def obtener_tasa_real():
    try:
        monitor = Monitor(AlCambio, 'USD')
        monitors_list = monitor.get_all_monitors()
        for m in monitors_list:
            if "BCV" in m.title:
                return float(m.price)
        return 341.74
    except:
        return 341.74

@app.route('/')
def index():
    tasa = obtener_tasa_real()
    hoy = datetime.now()
    dias_restantes = (FECHA_VENCIMIENTO - hoy).days
    return render_template('index.html', tasa=tasa, dias_restantes=dias_restantes)

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email')
    # Solo verificamos si el correo está en nuestra lista de autorizados
    if email in CORREOS_AUTORIZADOS:
        session['autenticado'] = True
        session['usuario'] = email
        return redirect(url_for('index'))
    return "Correo no autorizado", 401

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/preguntar', methods=['POST'])
def preguntar():
    if not session.get('autenticado'):
        return jsonify({"respuesta": "Acceso denegado."}), 401
    
    data = request.get_json()
    pregunta = data.get('pregunta', '').lower()
    tasa = obtener_tasa_real()
    
    try:
        if not os.path.exists(EXCEL_FILE):
            return jsonify({"respuesta": "Falta el archivo de inventario."})

        df = pd.read_excel(EXCEL_FILE)
        match = df[df['Producto'].str.contains(pregunta, case=False, na=False)]
        
        if not match.empty:
            prod = match.iloc[0]['Producto']
            usd = float(match.iloc[0]['Precio_USD'])
            bs = usd * tasa
            return jsonify({
                "respuesta": f"El {prod} cuesta {usd} dólares. En bolívares son {bs:.2f}.",
                "tasa_sync": tasa
            })
        return jsonify({"respuesta": f"No encontré '{pregunta}'."})
    except:
        return jsonify({"respuesta": "Error al consultar."}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)