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
# --- RUTAS ADMINISTRATIVAS COMPLETAS ---

@app.route('/admin')
def admin_panel():
    auth = request.args.get('auth_key')
    if auth != ADMIN_PASS: 
        return "No autorizado", 403
    
    try:
        # 1. Obtener usuarios y calcular estado de vencimiento
        usuarios_res = supabase.table("suscripciones").select("*").execute()
        usuarios = usuarios_res.data if usuarios_res.data else []
        hoy = datetime.now().date()
        
        for u in usuarios:
            try:
                vence = datetime.strptime(u['fecha_vencimiento'], '%Y-%m-%d').date()
                u['vencido'] = vence < hoy
            except:
                u['vencido'] = True

        # 2. Obtener Logs con mapeo de fecha para el HTML
        try:
            # Intentamos por created_at (estándar Supabase)
            logs_res = supabase.table("logs_actividad").select("*").order("created_at", desc=True).limit(100).execute()
        except:
            logs_res = supabase.table("logs_actividad").select("*").limit(100).execute()
        
        logs_raw = logs_res.data if logs_res.data else []
        logs = []
        for l in logs_raw:
            # Mapeamos 'created_at' a 'fecha' para que el HTML lo reconozca
            l['fecha'] = l.get('created_at', '2026-01-01T00:00:00')
            logs.append(l)

        # 3. Estadísticas para los cuadros superiores
        stats = {
            "total": len(usuarios),
            "activos": len([u for u in usuarios if not u['vencido']]),
            "vencidos": len([u for u in usuarios if u['vencido']])
        }

        # 4. Ranking de Salud (Búsquedas exitosas vs fallidas)
        from collections import Counter
        emails_actividad = [l['email'] for l in logs if l.get('email')]
        conteo = Counter(emails_actividad)
        
        ranking = []
        for email, count in conteo.most_common(5):
            logs_cliente = [l for l in logs if l['email'] == email]
            exitos = len([l for l in logs_cliente if l.get('exito') == True])
            total = len(logs_cliente)
            salud = int((exitos / total) * 100) if total > 0 else 0
            
            ranking.append({
                "email": email,
                "count": count,
                "salud": salud,
                "alerta": salud < 70  # Alerta visual si el éxito es bajo
            })
        
        return render_template('admin.html', 
                               usuarios=usuarios, 
                               stats=stats, 
                               logs=logs, 
                               ranking=ranking, 
                               admin_pass=ADMIN_PASS)
                               
    except Exception as e:
        print(f"ERROR EN PANEL ADMIN: {str(e)}")
        return f"Error interno: {str(e)}", 500

@app.route('/admin/crear', methods=['POST'])
def crear_usuario():
    auth = request.form.get('auth_key')
    if auth != ADMIN_PASS: return "Error de autenticación", 403
    
    email = request.form.get('email').lower().strip()
    data = {
        "email": email,
        "password": request.form.get('password'),
        "fecha_vencimiento": request.form.get('vence'),
        "activo": 1
    }
    
    try:
        supabase.table("suscripciones").insert(data).execute()
        # Redirigir de vuelta al panel con la llave
        return redirect(url_for('admin_panel', auth_key=ADMIN_PASS))
    except Exception as e:
        return f"Error al crear usuario: {str(e)}"

@app.route('/admin/eliminar', methods=['POST'])
def eliminar_usuario():
    auth = request.form.get('auth_key')
    if auth != ADMIN_PASS: return "Error de autenticación", 403
    
    email_a_eliminar = request.form.get('email')
    
    try:
        # 1. Eliminar suscripción
        supabase.table("suscripciones").delete().eq("email", email_a_eliminar).execute()
        # 2. Opcional: Eliminar su inventario de la DB para limpiar espacio
        supabase.table("inventarios").delete().eq("empresa_email", email_a_eliminar).execute()
        
        return redirect(url_for('admin_panel', auth_key=ADMIN_PASS))
    except Exception as e:
        return f"Error al eliminar: {str(e)}"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))