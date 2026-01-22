from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
import pandas as pd
import os
import io
from pyDolarVenezuela.pages import AlCambio
from pyDolarVenezuela import Monitor
from datetime import datetime
from supabase import create_client, Client
import time
from rapidfuzz import process, utils

app = Flask(__name__)
app.secret_key = 'elena_farmacia_2026_key'

# --- CONFIGURACIÓN ---
SUPABASE_URL = "https://kebpamfydhnxeaeegulx.supabase.co"
SUPABASE_KEY = "sb_secret_lSrahuG5Nv32T1ZaV7lfRw_WFXuiP4H"
ADMIN_PASS = "1234"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Memoria temporal para la Tasa (Diccionario por empresa para no mezclar)
memoria_tasa = {} 

MAPEO_COLUMNAS = {
    'Producto': ['producto', 'descripcion', 'nombre', 'articulo', 'item'],
    'Precio_USD': ['precio venta', 'pvp', 'precio', 'venta', 'precio_unitario', 'precio_usd', 'costo_usd'],
    'Stock': ['stock actual', 'stock', 'cantidad', 'existencia']
}

# --- FUNCIONES DE APOYO ---
def obtener_tasa_real():
    try:
        monitor = Monitor(AlCambio, 'USD')
        monitores = monitor.get_all_monitors()
        for m in monitores:
            if "BCV" in m.title:
                val = float(m.price)
                if 10 < val < 150: return val
        return 54.20
    except: return 54.20

def get_tasa_usuario(email):
    if email not in memoria_tasa:
        memoria_tasa[email] = {"tasa": obtener_tasa_real(), "manual": False}
    return memoria_tasa[email]

# --- RUTAS DE AUTENTICACIÓN ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').lower().strip()
        password = request.form.get('password')
        res = supabase.table("suscripciones").select("*").eq("email", email).eq("activo", 1).execute()
        if res.data:
            user = res.data[0]
            if user.get('password') == password:
                session.permanent = True
                session['logged_in'] = True 
                session['usuario'] = email
                session['fecha_vencimiento'] = user['fecha_vencimiento']
                return redirect(url_for('index'))
            else: return render_template('login.html', error="Clave incorrecta")
        return render_template('login.html', error="Usuario no registrado")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- RUTA PRINCIPAL ---
@app.route('/')
def index():
    if not session.get('logged_in'): return redirect(url_for('login'))
    
    email = session.get('usuario')
    datos_tasa = get_tasa_usuario(email)
    
    dias_restantes = 0
    if session.get('fecha_vencimiento'):
        try:
            vence = datetime.strptime(session['fecha_vencimiento'], '%Y-%m-%d').date()
            dias_restantes = (vence - datetime.now().date()).days
        except: pass
        
    return render_template('index.html', tasa=datos_tasa['tasa'], dias_restantes=dias_restantes, email=email)

# --- LÓGICA DE ELENA (BÚSQUEDA EN BASE DE DATOS) ---
@app.route('/preguntar', methods=['POST'])
def preguntar():
    t_inicio = time.time()
    data = request.get_json()
    usuario_email = session.get('usuario')
    if not usuario_email: return jsonify({"respuesta": "Sesión expirada"}), 401
    
    ip_cliente = request.headers.get('X-Forwarded-For', request.remote_addr)

    # 1. Manejo de tasa por empresa
    datos_tasa = get_tasa_usuario(usuario_email)
    if data.get('nueva_tasa'):
        try:
            datos_tasa["tasa"] = float(data.get('nueva_tasa'))
            datos_tasa["manual"] = True
            return jsonify({"respuesta": "Tasa actualizada", "tasa": datos_tasa["tasa"]})
        except: return jsonify({"respuesta": "Error en tasa"})

    pregunta_raw = data.get('pregunta', '').lower().strip()
    
    if "activar modo gerencia" in pregunta_raw:
        return jsonify({"respuesta": "Modo gerencia activo.", "modo_admin": True})

    # 2. OBTENER INVENTARIO DESDE SUPABASE (Filtrado por empresa)
    try:
        res_inv = supabase.table("inventarios").select("*").eq("empresa_email", usuario_email).execute()
        if not res_inv.data:
            return jsonify({"respuesta": "Elena: No tienes productos cargados. Sube tu inventario en modo Gerencia."})
        
        df = pd.DataFrame(res_inv.data)
    except Exception as e:
        return jsonify({"respuesta": f"Error al conectar con la base de datos: {str(e)}"})

    # 3. LIMPIEZA DE LENGUAJE NATURAL
    palabras_ruido = ["cuanto cuesta", "cuanto vale", "que precio tiene", "precio de", "dame el precio de", "tienes", "busco", "valor de", "precio"]
    pregunta_limpia = pregunta_raw
    for frase in palabras_ruido:
        pregunta_limpia = pregunta_limpia.replace(frase, "")
    pregunta_limpia = pregunta_limpia.strip()

    busqueda_exitosa = False
    try:
        # 4. Búsqueda Difusa sobre los datos de la empresa
        match = process.extractOne(
            pregunta_limpia, 
            df['producto'].astype(str).tolist(), 
            processor=utils.default_process
        )

        if match and match[1] > 60:
            nombre_p = match[0]
            fila = df[df['producto'] == nombre_p].iloc[0]
            
            p_usd = float(fila['precio_usd'])
            p_bs = p_usd * datos_tasa["tasa"]
            stock = fila.get('stock', '0')

            respuesta_final = f"El {nombre_p} cuesta {p_bs:,.2f} Bs, que son {p_usd:,.2f} $. Stock: {stock}"
            busqueda_exitosa = True
        else:
            respuesta_final = f"Lo siento, no encontré '{pregunta_limpia}' en tu inventario."
    except Exception as e:
        respuesta_final = f"Elena: Error en búsqueda ({str(e)})"

    # 5. LOGS EN SUPABASE
    try:
        supabase.table("logs_actividad").insert({
            "email": usuario_email,
            "accion": "CONSULTA_PRECIO",
            "detalle": pregunta_raw,
            "ip_address": ip_cliente,
            "exito": busqueda_exitosa
        }).execute()
    except: pass

    return jsonify({"respuesta": respuesta_final})

@app.route('/upload', methods=['POST'])
def upload():
    usuario_email = session.get('usuario')
    if not usuario_email: return jsonify({"success": False, "error": "No session"})
    
    file = request.files.get('archivo')
    if not file: return jsonify({"success": False})
    
    try:
        stream = io.BytesIO(file.read())
        df = pd.read_excel(stream) if file.filename.endswith('.xlsx') else pd.read_csv(stream)
        
        # Aplicar Mapeo de Columnas
        nuevas = {c: est for est, sin in MAPEO_COLUMNAS.items() for c in df.columns if str(c).lower().strip() in sin}
        df.rename(columns=nuevas, inplace=True)

        # Preparar datos para Supabase
        # Borrar inventario anterior de esta empresa
        supabase.table("inventarios").delete().eq("empresa_email", usuario_email).execute()
        
        registros = []
        for _, fila in df.iterrows():
            registros.append({
                "empresa_email": usuario_email,
                "producto": str(fila.get('Producto', 'Sin nombre')),
                "precio_usd": float(fila.get('Precio_USD', 0)),
                "stock": str(fila.get('Stock', '0'))
            })
        
        # Inserción masiva
        supabase.table("inventarios").insert(registros).execute()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

# --- PANEL ADMIN (Se mantiene igual pero conectado a suscripciones) ---
@app.route('/admin')
def admin_panel():
    auth = request.args.get('auth_key')
    if auth != ADMIN_PASS: return "No autorizado", 403
    try:
        usuarios = supabase.table("suscripciones").select("*").execute().data
        logs = supabase.table("logs_actividad").select("*").order("fecha", desc=True).limit(50).execute().data
        return render_template('admin.html', usuarios=usuarios, logs=logs, admin_pass=ADMIN_PASS)
    except Exception as e: return f"Error Admin: {e}", 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))