from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
import pandas as pd
import os
import io
from pyDolarVenezuela.pages import AlCambio
from pyDolarVenezuela import Monitor
from datetime import datetime, timedelta
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
        
        # Buscamos al usuario
        res = supabase.table("suscripciones").select("*").eq("email", email).execute()
        
        if res.data:
            user = res.data[0]
            
            # 1. Verificamos contraseña y estado básico
            if user.get('password') == password and user.get('activo') == 1:
                
                # --- AQUÍ ESTÁ EL BLOQUEO POR FECHA ---
                try:
                    fecha_vence = datetime.strptime(user['fecha_vencimiento'], '%Y-%m-%d').date()
                    hoy = datetime.now().date()
                    
                    # Definimos el límite: Fecha de vencimiento + 1 día de gracia
                    # Si vence el 22, puede entrar el 22 y el 23. El 24 ya NO.
                    limite_gracia = fecha_vence + timedelta(days=1)
                    
                    if hoy > limite_gracia:
                        return render_template('login.html', error="Suscripción expirada el " + str(fecha_vence) + ". Contacte soporte.")
                except Exception as e:
                    print(f"Error validando fecha: {e}")
                # --------------------------------------

                # Si pasó los filtros anteriores, entra al sistema
                session.permanent = True
                session['logged_in'] = True
                session['usuario'] = email
                session['fecha_vencimiento'] = user['fecha_vencimiento']
                return redirect(url_for('index'))
            
            return render_template('login.html', error="Credenciales incorrectas o cuenta inactiva")
        
        return render_template('login.html', error="Usuario no encontrado")
    
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
    if not usuario_email: 
        return jsonify({"respuesta": "Sesión expirada"}), 401
    
    # --- CAPTURA DE IDENTIFICADOR DE EQUIPO ---
    equipo_id = data.get('equipo_id', 'DESCONOCIDO')
    ip_cliente = request.headers.get('X-Forwarded-For', request.remote_addr)
    es_modo_admin = data.get('modo_admin', False)

    # 1. Manejo de tasa por empresa
    datos_tasa = get_tasa_usuario(usuario_email)
    
    # Lógica para actualización manual de tasa (vía input o voz)
    if data.get('nueva_tasa'):
        try:
            nueva_tasa_val = float(str(data.get('nueva_tasa')).replace(",", "."))
            datos_tasa["tasa"] = nueva_tasa_val
            datos_tasa["manual"] = True
            
            # Registro de log para cambio de tasa con equipo_id
            try:
                supabase.table("logs_actividad").insert({
                    "email": usuario_email,
                    "accion": "CAMBIO_TASA",
                    "detalle": f"Nueva tasa: {nueva_tasa_val}",
                    "ip_address": ip_cliente,
                    "equipo_id": equipo_id, # <--- INTEGRADO
                    "exito": True
                }).execute()
            except: pass

            return jsonify({
                "respuesta": f"Tasa actualizada a {nueva_tasa_val}", 
                "tasa": nueva_tasa_val,
                "exito_tasa": True
            })
        except: 
            return jsonify({"respuesta": "Error: El formato de tasa no es válido."})

    pregunta_raw = data.get('pregunta', '').lower().strip()
    
    # Comandos especiales
    if "activar modo gerencia" in pregunta_raw:
        return jsonify({"respuesta": "Modo gerencia activo.", "modo_admin": True})

    # 2. OBTENER INVENTARIO DESDE SUPABASE
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
        # 4. Búsqueda Difusa (Fuzzy Match)
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
            
            val_bs_visual = f"{p_bs:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            val_usd_visual = f"{p_usd:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

            texto_bs_audio = f"{p_bs:.2f}".replace(".", " con ")
            texto_usd_audio = f"{p_usd:.2f}".replace(".00", "").replace(".", " con ")

            nombre_audio = nombre_p.lower()
            reemplazos = {" mg": " miligramos", "mg": " miligramos", " ml": " mililitros", "ml": " mililitros", " g ": " gramos ", " gr ": " gramos "}
            for k, v in reemplazos.items():
                nombre_audio = nombre_audio.replace(k, v)

            respuesta_voz = f"El {nombre_audio} cuesta {texto_bs_audio} Bolívares."
            
            stock_val = "0"
            if es_modo_admin:
                stock_val = str(fila.get('stock', '0'))
                respuesta_voz += f" El stock actual es de {stock_val} unidades."
            
            busqueda_exitosa = True
            
            # Registro de log antes del retorno exitoso
            try:
                supabase.table("logs_actividad").insert({
                    "email": usuario_email,
                    "accion": "CONSULTA_PRECIO",
                    "detalle": pregunta_raw,
                    "ip_address": ip_cliente,
                    "equipo_id": equipo_id, # <--- INTEGRADO
                    "exito": True
                }).execute()
            except: pass

            return jsonify({
                "exito": True,
                "producto_nombre": nombre_p,
                "p_bs": val_bs_visual,
                "p_usd": val_usd_visual,
                "respuesta": respuesta_voz,
                "modo_admin": es_modo_admin
            })

        else:
            respuesta_final = f"Lo siento, no encontré '{pregunta_limpia}' en el inventario."
            
            # Log de búsqueda fallida
            try:
                supabase.table("logs_actividad").insert({
                    "email": usuario_email,
                    "accion": "CONSULTA_PRECIO",
                    "detalle": pregunta_raw,
                    "ip_address": ip_cliente,
                    "equipo_id": equipo_id, # <--- INTEGRADO
                    "exito": False
                }).execute()
            except: pass

            return jsonify({"exito": False, "respuesta": respuesta_final})

    except Exception as e:
        return jsonify({"exito": False, "respuesta": f"Elena: Error en búsqueda ({str(e)})"})
@app.route('/upload', methods=['POST'])
def upload_file():
    usuario_email = session.get('usuario')
    if not usuario_email: return jsonify({"success": False, "error": "No login"}), 401
    
    file = request.files.get('archivo')
    if not file: return jsonify({"success": False, "error": "No file"})

    try:
        # 1. Leer Excel (Intentamos detectar dónde empiezan los datos reales)
        df = pd.read_excel(file)
        
        # SI el Excel tiene filas vacías o basura arriba, buscamos la fila de títulos
        if not any(x in str(df.columns).lower() for x in ['producto', 'precio', 'articulo']):
            for i in range(10): # Buscamos en las primeras 10 filas
                df = pd.read_excel(file, skiprows=i+1)
                if any(x in str(df.columns).lower() for x in ['producto', 'precio', 'articulo']):
                    break

        # 2. Encontrar columnas automáticamente
        cols_encontradas = encontrar_columnas_maestras(df.columns)
        
        if 'producto' not in cols_encontradas or 'precio' not in cols_encontradas:
            return jsonify({"success": False, "error": "No detecto columnas de Producto o Precio"})

        # 3. Limpiar y Estandarizar Datos
        df_limpio = pd.DataFrame()
        df_limpio['producto'] = df[cols_encontradas['producto']].astype(str).str.upper().str.strip()
        df_limpio['precio_usd'] = df[cols_encontradas['precio']].apply(limpiar_precio)
        
        if 'stock' in cols_encontradas:
            df_limpio['stock'] = df[cols_encontradas['stock']].fillna(0).astype(int)
        else:
            df_limpio['stock'] = 0

        df_limpio['empresa_email'] = usuario_email

        # 4. Guardar en Supabase (Borrar anterior y subir nuevo)
        supabase.table("inventarios").delete().eq("empresa_email", usuario_email).execute()
        
        # Subir por bloques para no saturar la conexión
        datos_finales = df_limpio.to_dict(orient='records')
        for i in range(0, len(datos_finales), 100):
            supabase.table("inventarios").insert(datos_finales[i:i+100]).execute()

        return jsonify({"success": True, "productos": len(datos_finales)})

    except Exception as e:
        print(f"Error en carga: {str(e)}")
        return jsonify({"success": False, "error": str(e)})
# --- PANEL ADMIN (Se mantiene igual pero conectado a suscripciones) ---
# --- RUTAS ADMINISTRATIVAS COMPLETAS ---
def limpiar_precio(valor):
    """Convierte 'Ref 1.50$', '1,50' o ' 2.00 ' en float 1.50"""
    if pd.isna(valor) or valor == '': return 0.0
    try:
        s = str(valor).lower()
        # Eliminar todo lo que no sea número, punto o coma
        s = ''.join(c for c in s if c.isdigit() or c in '.,')
        s = s.replace(',', '.') # Estandarizar decimales
        # Si hay más de un punto (error de tipeo), dejamos solo el último
        if s.count('.') > 1:
            partes = s.split('.')
            s = "".join(partes[:-1]) + "." + partes[-1]
        return float(s)
    except:
        return 0.0

def encontrar_columnas_maestras(columnas):
    """Identifica Producto, Precio y Stock entre nombres caóticos"""
    mapeo = {
        'producto': ['producto', 'descripcion', 'nombre', 'articulo', 'item', 'descrip'],
        'precio': ['precio', 'pvp', 'venta', 'usd', 'ref', 'dolar', 'p.v.p'],
        'stock': ['stock', 'cantidad', 'existencia', 'disponible', 'cant', 'unidades']
    }
    resultado = {}
    for clave, variaciones in mapeo.items():
        for col in columnas:
            if any(v in str(col).lower() for v in variaciones):
                resultado[clave] = col
                break
    return resultado
@app.route('/admin')
def admin_panel():
    auth = request.args.get('auth_key')
    if auth != ADMIN_PASS: 
        return "No autorizado", 403
    
    try:
        # 1. Obtener usuarios y calcular estado de vencimiento
        # 1. Obtener usuarios y calcular estado de vencimiento (CON DÍA DE GRACIA)
        usuarios_res = supabase.table("suscripciones").select("*").execute()
        usuarios = usuarios_res.data if usuarios_res.data else []
        hoy = datetime.now().date()
        
        from datetime import timedelta # Asegúrate de tener esta importación arriba

        for u in usuarios:
            try:
                vence = datetime.strptime(u['fecha_vencimiento'], '%Y-%m-%d').date()
                
                # REGLA: Solo está vencido si HOY es mayor que (Fecha Vencimiento + 1 día)
                limite_gracia = vence + timedelta(days=1)
                u['vencido'] = hoy > limite_gracia
                
                # Opcional: Agregar una marca para saber si está en periodo de gracia
                u['en_gracia'] = (hoy > vence and hoy <= limite_gracia)
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
# --- PANEL ADMINISTRATIVO (ADMIN) ---
@app.route('/admin')
def admin():
    # 1. Seguridad básica: solo tú entras con la clave en la URL (ej: /admin?pass=1234)
    if request.args.get('pass') != ADMIN_PASS:
        return "Acceso denegado", 403

    # 2. Obtener datos de Supabase
    res_usuarios = supabase.table("suscripciones").select("*").execute()
    res_logs = supabase.table("logs_actividad").select("*").order("fecha", desc=True).execute()
    
    logs_data = res_logs.data
    usuarios_data = res_usuarios.data

    # --- INICIO DEL SÚPER RESUMEN DE TRÁFICO ---
    from collections import Counter
    
    conteo_diario = {}
    for log in logs_data:
        # Extraemos solo la fecha (YYYY-MM-DD) del timestamp de Supabase
        fecha = log['fecha'].split('T')[0]
        email = log['email']
        
        if email not in conteo_diario:
            conteo_diario[email] = Counter()
        conteo_diario[email][fecha] += 1

    # Estructura limpia para el HTML
    resumen_uso = []
    for email, conteos in conteo_diario.items():
        # Tomamos los últimos 7 días con actividad
        dias = [{"fecha": f, "cantidad": c} for f, c in sorted(conteos.items(), reverse=True)[:7]]
        resumen_uso.append({"email": email, "actividad": dias})
    # --- FIN DEL RESUMEN ---

    # 3. Calcular estadísticas rápidas para los cuadritos superiores
    hoy = datetime.now().date()
    stats = {
        "total": len(usuarios_data),
        "activos": sum(1 for u in usuarios_data if datetime.strptime(u['fecha_vencimiento'], '%Y-%m-%d').date() >= hoy),
        "vencidos": sum(1 for u in usuarios_data if datetime.strptime(u['fecha_vencimiento'], '%Y-%m-%d').date() < hoy)
    }

    # 4. Enviar todo al HTML
    return render_template(
        'admin.html', 
        usuarios=usuarios_data, 
        logs=logs_data, 
        stats=stats, 
        resumen_uso=resumen_uso, # <--- Esta es la variable que alimenta los chips de tráfico
        admin_pass=ADMIN_PASS
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))