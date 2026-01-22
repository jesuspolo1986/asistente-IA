from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
import pandas as pd
import os
import io
from pyDolarVenezuela.pages import AlCambio
from pyDolarVenezuela import Monitor
from datetime import datetime, timedelta
from supabase import create_client, Client
import time
app = Flask(__name__)
app.secret_key = 'elena_farmacia_2026_key'

# --- CONFIGURACIÓN ---
SUPABASE_URL = "https://kebpamfydhnxeaeegulx.supabase.co"
SUPABASE_KEY = "sb_secret_lSrahuG5Nv32T1ZaV7lfRw_WFXuiP4H"
ADMIN_PASS = "1234"
EXCEL_FILE = 'inventario.xlsx'

inventario_memoria = {"df": None, "tasa": 54.20}

# Mapeo según tu CSV: "Precio Venta" -> Precio_USD
MAPEO_COLUMNAS = {
    'Producto': ['producto', 'descripcion', 'nombre', 'articulo', 'item'],
    'Precio_USD': ['precio venta', 'pvp', 'precio', 'venta', 'precio_unitario', 'precio_usd', 'costo_usd'],
    'Stock': ['stock actual', 'stock', 'cantidad', 'existencia']
}

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
from flask import Flask, render_template, request, redirect, session, url_for

# ... (tus configuraciones previas de Supabase y ADMIN_PASS)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email').lower().strip()
        password = request.form.get('password')

        # 1. Buscamos al usuario por email en Supabase
        res = supabase.table("suscripciones").select("*").eq("email", email).execute()
        
        if res.data:
            user = res.data[0]
            # 2. Verificamos la clave maestra
            if user.get('password') == password:
                # 3. Guardamos la sesión
                session['user_email'] = email
                session['logged_in'] = True
                return redirect(url_for('index')) # Redirige a Elena
            else:
                return render_template('login.html', error="Clave incorrecta")
        else:
            return render_template('login.html', error="Empresa no registrada")

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- PROTECCIÓN DE LA RUTA PRINCIPAL ---
@app.route('/')
def index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('index.html', email=session['user_email'])
def obtener_tasa_real():
    try:
        monitor = Monitor(AlCambio, 'USD')
        monitores = monitor.get_all_monitors()
        for m in monitores:
            if "BCV" in m.title:
                val = float(m.price)
                if 10 < val < 100: return val
        return 54.20
    except: return 54.20

@app.route('/')
def index():
    if "tasa_manual" not in inventario_memoria:
        inventario_memoria["tasa"] = obtener_tasa_real()
    
    tasa = inventario_memoria["tasa"]
    dias_restantes = 1
    if session.get('autenticado') and session.get('fecha_vencimiento'):
        try:
            vence = datetime.strptime(session['fecha_vencimiento'], '%Y-%m-%d').date()
            dias_restantes = (vence - datetime.now().date()).days
        except: pass
    return render_template('index.html', tasa=tasa, dias_restantes=dias_restantes)

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files.get('archivo')
    if not file: return jsonify({"success": False, "mensaje": "Sin archivo"})
    try:
        stream = io.BytesIO(file.read())
        if file.filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(stream, engine='openpyxl')
        else:
            df = pd.read_csv(stream)
        
        nuevas = {c: est for est, sin in MAPEO_COLUMNAS.items() for c in df.columns if str(c).lower().strip() in sin}
        df.rename(columns=nuevas, inplace=True)
        df.columns = [str(c).strip() for c in df.columns]
        
        inventario_memoria["df"] = df
        stream.seek(0)
        with open(EXCEL_FILE, "wb") as f: f.write(stream.getbuffer())
        return jsonify({"success": True, "mensaje": "Inventario cargado"})
    except Exception as e: return jsonify({"success": False, "error": str(e)})
from collections import Counter

from collections import Counter

@app.route('/admin')
def admin_panel():
    auth = request.args.get('auth_key')
    if auth != ADMIN_PASS: 
        return "Acceso Denegado: Llave incorrecta", 403
    
    try:
        # 1. Obtener datos de Supabase
        res_usuarios = supabase.table("suscripciones").select("*").execute()
        usuarios = res_usuarios.data
        
        # Traemos los últimos 100 logs para un análisis de salud confiable
        res_logs = supabase.table("logs_actividad").select("*").order("fecha", desc=True).limit(100).execute()
        logs = res_logs.data
        
        # 2. PROCESAR RANKING Y SALUD (FAIL-CHECK)
        emails_en_logs = [l['email'] for l in logs if l['email']]
        conteo_actividad = Counter(emails_en_logs)
        
        ranking = []
        for email, count in conteo_actividad.most_common(5): # Top 5 empresas
            # Analizar logs específicos de esta empresa
            logs_empresa = [l for l in logs if l['email'] == email]
            exitosos = len([l for l in logs_empresa if l['exito'] == True])
            
            # Calcular % de salud (búsquedas exitosas vs totales)
            salud = (exitosos / len(logs_empresa)) * 100 if logs_empresa else 0
            
            ranking.append({
                "email": email,
                "count": count,
                "salud": round(salud),
                "alerta": salud < 70  # Alerta si fallan más del 30% de las veces
            })

        # 3. ESTADÍSTICAS DE SUSCRIPCIÓN
        hoy = datetime.now().date()
        stats = {"activos": 0, "vencidos": 0, "total": len(usuarios)}
        
        for u in usuarios:
            vence = datetime.strptime(u['fecha_vencimiento'], '%Y-%m-%d').date()
            u['vencido'] = vence < hoy
            if u['vencido']: 
                stats["vencidos"] += 1
            else: 
                stats["activos"] += 1
        
        return render_template('admin.html', 
                               usuarios=usuarios, 
                               stats=stats, 
                               logs=logs, 
                               ranking=ranking,
                               admin_pass=ADMIN_PASS)

    except Exception as e:
        return f"Error crítico en el Panel Admin: {str(e)}", 500from rapidfuzz import process, utils

import time

@app.route('/preguntar', methods=['POST'])
def preguntar():
    t_inicio = time.time() # Iniciamos cronómetro para medir rendimiento
    data = request.get_json()
    
    # Identificación del cliente (B2B)
    usuario_email = session.get('usuario', 'invitado@anonimo.com')
    ip_cliente = request.headers.get('X-Forwarded-For', request.remote_addr)

    # 1. Manejo de Tasa Manual (Gerencia)
    if data.get('nueva_tasa'):
        try:
            inventario_memoria["tasa"] = float(data.get('nueva_tasa'))
            inventario_memoria["tasa_manual"] = True
            return jsonify({"respuesta": "Tasa actualizada", "tasa": inventario_memoria["tasa"]})
        except: return jsonify({"respuesta": "Error en tasa"})

    pregunta_raw = data.get('pregunta', '').lower().strip()
    
    # 2. Acceso a Gerencia
    if "activar modo gerencia" in pregunta_raw:
        return jsonify({"respuesta": "Modo gerencia activo.", "modo_admin": True})

    # 3. Verificación de Inventario
    df = inventario_memoria["df"]
    if df is None:
        if os.path.exists(EXCEL_FILE):
            df = pd.read_excel(EXCEL_FILE, engine='openpyxl') if EXCEL_FILE.endswith('.xlsx') else pd.read_csv(EXCEL_FILE)
            inventario_memoria["df"] = df
        else:
            return jsonify({"respuesta": "Elena no tiene datos. Por favor, sube el inventario en el panel de gerencia."})

    # 4. Limpieza de lenguaje natural
    palabras_ruido = ["cuanto cuesta", "cuanto vale", "que precio tiene", "precio de", "dame el precio", "tienes", "busco", "valor"]
    pregunta_limpia = pregunta_raw
    for frase in palabras_ruido:
        pregunta_limpia = pregunta_limpia.replace(frase, "")
    pregunta_limpia = pregunta_limpia.strip()

    tasa = inventario_memoria["tasa"]
    respuesta_final = ""
    busqueda_exitosa = False

    try:
        # 5. Búsqueda Difusa
        resultados = process.extract(
            pregunta_limpia, 
            df['Producto'].astype(str).tolist(), 
            limit=5, 
            processor=utils.default_process
        )
        
        matches_validos = [r for r in resultados if r[1] > 60]

        if not matches_validos:
            respuesta_final = f"Lo siento, no encontré '{pregunta_limpia}' en el inventario."
            busqueda_exitosa = False
        
        elif len(matches_validos) == 1 or matches_validos[0][1] > 90:
            nombre_match = matches_validos[0][0]
            fila = df[df['Producto'] == nombre_match].iloc[0]
            p_usd = float(fila['Precio_USD'])
            p_bs = p_usd * tasa
            stock = fila['Stock'] if 'Stock' in fila.columns else "?"
            
            respuesta_final = f"El {nombre_match} cuesta {p_usd:,.2f} $, que son {p_bs:,.2f} Bs. Quedan {stock} unidades."
            busqueda_exitosa = True

        else:
            opciones = []
            for m in matches_validos[:3]:
                nombre_p = m[0]
                f_p = df[df['Producto'] == nombre_p].iloc[0]
                u_p = float(f_p['Precio_USD'])
                b_p = u_p * tasa
                opciones.append(f"{nombre_p} en {u_p}$ ({b_p:,.2f} Bs)")
            
            respuesta_final = f"Encontré varias opciones: {' . también tengo . '.join(opciones)}. ¿Cuál buscabas?"
            busqueda_exitosa = True

    except Exception as e:
        respuesta_final = f"Error en la búsqueda: {str(e)}"
        busqueda_exitosa = False

    # --- SISTEMA DE MONITOREO B2B ---
    # Registramos la actividad silenciosamente en Supabase
    try:
        t_respuesta = round(time.time() - t_inicio, 3)
        supabase.table("logs_actividad").insert({
            "email": usuario_email,
            "accion": "CONSULTA_PRECIO",
            "detalle": pregunta_raw,
            "ip_address": ip_cliente,
            "duracion_respuesta": t_respuesta,
            "exito": busqueda_exitosa
        }).execute()
    except Exception as log_err:
        print(f"Error de monitoreo: {log_err}")

    return jsonify({"respuesta": respuesta_final})
@app.route('/admin/crear', methods=['POST'])
def crear_usuario():
    auth = request.form.get('auth_key')
    if auth != ADMIN_PASS: return "Acceso Denegado", 403
    
    # Capturamos los datos del formulario
    email = request.form.get('email', '').lower().strip()
    vence = request.form.get('vence')
    password = request.form.get('password') # <-- NUEVO: Captura la clave maestra

    try:
        # Insertamos en la tabla de Supabase incluyendo la contraseña
        supabase.table("suscripciones").insert({
            "email": email, 
            "fecha_vencimiento": vence, 
            "password": password, # <-- NUEVO: Se guarda en la BD
            "activo": 1,
            "plan": "Mensual",
            "creditos_totales": 50
        }).execute()
        
        return redirect(url_for('admin_panel', auth_key=ADMIN_PASS))
    except Exception as e:
        return f"Error al crear usuario: {str(e)}"
@app.route('/admin/eliminar', methods=['POST'])
def eliminar_usuario():
    auth = request.form.get('auth_key')
    if auth != ADMIN_PASS: return "Acceso Denegado", 403
    
    email = request.form.get('email')
    
    try:
        # Eliminamos de la tabla de Supabase
        supabase.table("suscripciones").delete().eq("email", email).execute()
        return redirect(url_for('admin_panel', auth_key=ADMIN_PASS))
    except Exception as e:
        return f"Error al eliminar: {str(e)}"
@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email', '').lower().strip()
    res = supabase.table("suscripciones").select("*").eq("email", email).eq("activo", 1).execute()
    if res.data:
        session['autenticado'] = True
        session['usuario'] = email
        session['fecha_vencimiento'] = res.data[0]['fecha_vencimiento']
        return redirect(url_for('index'))
    return "No autorizado", 401

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))