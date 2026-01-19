from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
import pandas as pd
import os
from pyDolarVenezuela.pages import AlCambio
from pyDolarVenezuela import Monitor
from datetime import datetime
from supabase import create_client, Client

app = Flask(__name__)
app.secret_key = 'elena_farmacia_2026_key'

# --- CONFIGURACIÓN ---
SUPABASE_URL = "https://kebpamfydhnxeaeegulx.supabase.co"
SUPABASE_KEY = "sb_secret_lSrahuG5Nv32T1ZaV7lfRw_WFXuiP4H" 
EXCEL_FILE = 'inventario.xlsx'

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def obtener_tasa_real():
    print("📡 Consultando AlCambio para Elena...")
    try:
        monitor = Monitor(AlCambio, 'USD')
        monitores = monitor.get_all_monitors()
        
        tasa_final = None

        # Buscamos en la lista según tu prueba
        for m in monitores:
            # Si encontramos el monitor del BCV
            if "BCV" in m.title:
                val = float(m.price)
                # SEGURO: Si el valor es el error 341.74, buscamos otro o usamos respaldo
                if val > 100: 
                    continue 
                tasa_final = val
                break
        
        # Si no encontramos BCV válido, intentamos con AlCambio o el primero que no sea 0.01
        if not tasa_final:
            for m in monitores:
                val = float(m.price)
                if 10 < val < 100: # Rango razonable para el dólar hoy
                    tasa_final = val
                    break

        # Si todo falla, tasa de respaldo manual (19 de enero)
        return tasa_final if tasa_final else 54.20

    except Exception as e:
        print(f"❌ Error en tasa: {e}")
        return 54.20

@app.route('/')
def index():
    tasa = obtener_tasa_real()
    # Para el banner de suscripción
    dias_restantes = 10 
    if session.get('autenticado') and session.get('fecha_vencimiento'):
        try:
            vence = datetime.strptime(session['fecha_vencimiento'], '%Y-%m-%d')
            dias_restantes = (vence.date() - datetime.now().date()).days
        except: pass
    return render_template('index.html', tasa=tasa, dias_restantes=dias_restantes)

@app.route('/subir_excel', methods=['POST'])
def subir_excel():
    if 'archivo' not in request.files:
        flash("No se detectó el archivo", "danger")
        return redirect(url_for('index'))
    
    file = request.files['archivo']
    if file and file.filename.endswith('.xlsx'):
        # Guardar con ruta absoluta para evitar errores en Koyeb
        base_path = os.path.dirname(os.path.abspath(__file__))
        file.save(os.path.join(base_path, EXCEL_FILE))
        flash("¡Inventario actualizado con éxito!", "success")
        return redirect(url_for('index'))
    
    flash("Error: Formato inválido (.xlsx)", "danger")
    return redirect(url_for('index'))

@app.route('/preguntar', methods=['POST'])
def preguntar():
    if not session.get('autenticado'): return jsonify({"respuesta": "Inicia sesión."}), 401
    
    data = request.get_json()
    pregunta = data.get('pregunta', '').lower().strip()
    
    if "activar modo gerencia" in pregunta:
        return jsonify({"respuesta": "Modo gerencia activo. Panel de carga desbloqueado.", "modo_admin": True})

    tasa = obtener_tasa_real()
    
    try:
        if not os.path.exists(EXCEL_FILE):
            return jsonify({"respuesta": "Elena no tiene el inventario. Por favor, súbelo en modo gerencia."})
        
        # IMPORTANTE: engine='openpyxl' para evitar el error anterior
        df = pd.read_excel(EXCEL_FILE, engine='openpyxl')
        
        match = df[df['Producto'].str.contains(pregunta, case=False, na=False)]
        
        if not match.empty:
            p = match.iloc[0]['Producto']
            u = float(match.iloc[0]['Precio_USD'])
            return jsonify({"respuesta": f"El {p} cuesta {u}$. A tasa {tasa} son {u*tasa:.2f} Bs."})
        
        return jsonify({"respuesta": f"No encontré '{pregunta}' en el inventario."})
    except Exception as e:
        return jsonify({"respuesta": f"Error al leer el archivo: {str(e)}"})

# (Aquí van tus rutas de login y logout iguales a las anteriores)