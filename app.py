from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import pandas as pd
import os
from pyDolarVenezuela.pages import AlCambio
from pyDolarVenezuela import Monitor
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'elena_farmacia_secret_2026'

# --- CONFIGURACIÓN ---
EXCEL_FILE = 'inventario.xlsx'
USUARIO_ADMIN = "farmacia@admin.com"
PASSWORD_ADMIN = "1234" # Cambia esto por tu clave real
FECHA_VENCIMIENTO = datetime(2026, 1, 17) # Ejemplo: venció ayer

def obtener_tasa_real():
    try:
        monitor = Monitor(AlCambio, 'USD')
        monitores = monitor.get_all_monitors()
        for m in monitores:
            if "BCV" in m.title:
                return float(m.price)
        return 341.74
    except:
        return 341.74

def calcular_gracia():
    hoy = datetime.now()
    dias_diff = (FECHA_VENCIMIENTO - hoy).days
    return dias_diff # Si es -1, está en periodo de gracia

@app.route('/')
def index():
    tasa = obtener_tasa_real()
    dias = calcular_gracia()
    return render_template('index.html', tasa=tasa, dias_restantes=dias)

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email')
    password = request.form.get('password')
    
    if email == USUARIO_ADMIN and password == PASSWORD_ADMIN:
        session['autenticado'] = True
        return redirect(url_for('index'))
    return "Credenciales incorrectas", 401

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/preguntar', methods=['POST'])
def preguntar():
    if not session.get('autenticado'):
        return jsonify({"respuesta": "Inicia sesión primero."}), 401
    
    data = request.get_json()
    pregunta = data.get('pregunta', '').lower()
    tasa = obtener_tasa_real()
    
    try:
        df = pd.read_excel(EXCEL_FILE)
        # Búsqueda de producto
        match = df[df['Producto'].str.contains(pregunta, case=False, na=False)]
        
        if not match.empty:
            prod = match.iloc[0]['Producto']
            usd = float(match.iloc[0]['Precio_USD'])
            bs = usd * tasa
            return jsonify({
                "respuesta": f"El {prod} cuesta {usd} dólares. Al cambio son {bs:.2f} bolívares.",
                "tasa_sync": tasa
            })
        return jsonify({"respuesta": "No encontré ese producto."})
    except Exception as e:
        return jsonify({"respuesta": f"Error: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)