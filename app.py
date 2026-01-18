from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import pandas as pd
import os
from pyDolarVenezuela.pages import AlCambio
from pyDolarVenezuela import Monitor

app = Flask(__name__)
app.secret_key = 'elena_farmacia_secret_2026'

# --- CONFIGURACIÓN ---
EXCEL_FILE = 'inventario.xlsx'
USUARIO_ADMIN = "farmacia@admin.com"
PASSWORD_ADMIN = "1234" 

def obtener_tasa_real():
    try:
        # Usamos AlCambio para obtener el 341.74 que necesitas
        monitor = Monitor(AlCambio, 'USD')
        monitors_list = monitor.get_all_monitors()
        for m in monitors_list:
            if "BCV" in m.title:
                return float(m.price)
        return 341.74
    except Exception as e:
        print(f"Error tasa: {e}")
        return 341.74

@app.route('/')
def index():
    tasa = obtener_tasa_real()
    return render_template('index.html', tasa=tasa)

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email')
    password = request.form.get('password')
    if email == USUARIO_ADMIN and password == PASSWORD_ADMIN:
        session['autenticado'] = True
        return redirect(url_for('index'))
    return "Error: Credenciales no válidas", 401

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/preguntar', methods=['POST'])
def preguntar():
    if not session.get('autenticado'):
        return jsonify({"respuesta": "Por favor, inicia sesión."}), 401
    
    data = request.get_json()
    pregunta = data.get('pregunta', '').lower()
    tasa = obtener_tasa_real()
    
    try:
        # Verificamos si existe el Excel en el servidor
        if not os.path.exists(EXCEL_FILE):
            return jsonify({"respuesta": "El archivo de inventario no está cargado en el servidor."})

        df = pd.read_excel(EXCEL_FILE)
        match = df[df['Producto'].str.contains(pregunta, case=False, na=False)]
        
        if not match.empty:
            prod = match.iloc[0]['Producto']
            usd = float(match.iloc[0]['Precio_USD'])
            bs = usd * tasa
            return jsonify({
                "respuesta": f"El {prod} cuesta {usd} dólares. Al cambio de hoy son {bs:.2f} bolívares.",
                "tasa_sync": tasa
            })
        return jsonify({"respuesta": f"No encontré '{pregunta}' en el inventario."})
    except Exception as e:
        return jsonify({"respuesta": f"Hubo un error al leer los datos."}), 500

if __name__ == '__main__':
    # Koyeb usa la variable de entorno PORT
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)