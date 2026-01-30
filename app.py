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
@app.route('/obtener_tasa_actual', methods=['GET'])
def obtener_tasa_actual():
    usuario_email = session.get('usuario')
    if not usuario_email:
        return jsonify({"error": "No session"}), 401
    
    datos_tasa = get_tasa_usuario(usuario_email)
    return jsonify({"tasa": datos_tasa["tasa"]})

def get_tasa_usuario(email):
    # PRIORIDAD 1: ¿Está en la memoria RAM? (Rapidez)
    if email in memoria_tasa:
        return memoria_tasa[email]
    
    # PRIORIDAD 2: ¿El usuario tiene una tasa fija en su suscripción?
    try:
        res_sub = supabase.table("suscripciones").select("tasa_personalizada").eq("email", email).execute()
        if res_sub.data and res_sub.data[0].get('tasa_personalizada'):
            t_val = float(res_sub.data[0]['tasa_personalizada'])
            memoria_tasa[email] = {"tasa": t_val, "manual": True, "fecha": "PERFIL"}
            return memoria_tasa[email]
    except: pass

    # PRIORIDAD 3: LA TASA MAESTRA DEL ADMINISTRADOR
    try:
        res_global = supabase.table("ajustes_sistema").select("valor").eq("clave", "tasa_maestra").execute()
        if res_global.data:
            t_maestra = float(res_global.data[0]['valor'])
            # Guardamos en RAM para este usuario específico
            memoria_tasa[email] = {"tasa": t_maestra, "manual": True, "fecha": "GLOBAL"}
            return memoria_tasa[email]
    except: pass

    # PRIORIDAD 4: BCV (Fallback final)
    tasa_bcv = obtener_tasa_real()
    return {"tasa": tasa_bcv, "manual": False, "fecha": "BCV"}
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
        return jsonify({"respuesta": "Sesión expirada. Por favor, inicia sesión de nuevo."}), 401
    
    # --- CAPTURA DE IDENTIFICADOR DE EQUIPO ---
    equipo_id = data.get('equipo_id', 'DESCONOCIDO')
    ip_cliente = request.headers.get('X-Forwarded-For', request.remote_addr)
    es_modo_admin = data.get('modo_admin', False)

    # ========================================================
    # 1. SEGURIDAD: LÓGICA DE BLOQUEO POR LÍMITE DE EQUIPOS
    # ========================================================
    try:
        res_sub = supabase.table("suscripciones").select("limite_equipos").eq("email", usuario_email).execute()
        limite_permitido = res_sub.data[0].get('limite_equipos', 1) if res_sub.data else 1

        res_logs = supabase.table("logs_actividad").select("equipo_id").eq("email", usuario_email).eq("exito", True).execute()
        # Obtenemos IDs únicos ya registrados para este usuario
        equipos_registrados = {l['equipo_id'] for l in res_logs.data if l.get('equipo_id') and l['equipo_id'] != 'DESCONOCIDO'}

        if equipo_id != 'DESCONOCIDO' and equipo_id not in equipos_registrados:
            if len(equipos_registrados) >= limite_permitido:
                return jsonify({
                    "exito": False,
                    "respuesta": f"🚫 ACCESO RESTRINGIDO: Tu plan permite {limite_permitido} equipo(s). Contacta a soporte para ampliarlo."
                })
    except Exception as e:
        print(f"⚠️ Error validando límites (bypass por seguridad): {e}")

    # ========================================================
    # 2. GESTIÓN DE TASA (CONSULTA Y ACTUALIZACIÓN)
    # ========================================================
    # Si viene una nueva tasa en la petición, la actualizamos primero
    if data.get('nueva_tasa'):
        try:
            nueva_tasa_val = float(str(data.get('nueva_tasa')).replace(",", "."))
            
            # A. Persistencia en Supabase (PRIMERO LA DB para asegurar permanencia)
            supabase.table("suscripciones").update({
                "tasa_personalizada": nueva_tasa_val
            }).eq("email", usuario_email).execute()

            # B. Actualizar RAM (Para respuesta inmediata en otros equipos)
            memoria_tasa[usuario_email] = {
                "tasa": nueva_tasa_val,
                "manual": True,
                "fecha": datetime.now().strftime("%Y-%m-%d")
            }

            # C. Log del cambio
            try:
                supabase.table("logs_actividad").insert({
                    "email": usuario_email, "accion": "CAMBIO_TASA", 
                    "detalle": f"Nueva tasa: {nueva_tasa_val}", "ip_address": ip_cliente,
                    "equipo_id": equipo_id, "exito": True
                }).execute()
            except: pass

            return jsonify({
                "respuesta": f"Tasa actualizada correctamente a {nueva_tasa_val} Bs.", 
                "tasa": nueva_tasa_val,
                "exito_tasa": True
            })
        except Exception as e: 
            return jsonify({"respuesta": "Formato de tasa no válido."})

    # Obtener tasa usando la función persistente
    datos_tasa = get_tasa_usuario(usuario_email)
    
    pregunta_raw = data.get('pregunta', '').lower().strip()
    if "activar modo gerencia" in pregunta_raw:
        return jsonify({"respuesta": "Modo gerencia activo.", "modo_admin": True})

    # ========================================================
    # 3. PROCESAMIENTO DE INVENTARIO Y BÚSQUEDA
    # ========================================================
    try:
        res_inv = supabase.table("inventarios").select("*").eq("empresa_email", usuario_email).execute()
        if not res_inv.data:
            return jsonify({"respuesta": "Elena: No hay productos en tu inventario. Sube un Excel primero."})
        
        df = pd.DataFrame(res_inv.data)
    except Exception as e:
        return jsonify({"respuesta": f"Error de conexión con la base de datos."})

    # Limpieza de pregunta
    palabras_ruido = ["cuanto cuesta", "cuanto vale", "que precio tiene", "precio de", "dame el precio de", "precio"]
    pregunta_limpia = pregunta_raw
    for frase in palabras_ruido:
        pregunta_limpia = pregunta_limpia.replace(frase, "")
    pregunta_limpia = pregunta_limpia.strip()

    try:
        # Búsqueda difusa optimizada
        match = process.extractOne(
            pregunta_limpia, 
            df['producto'].astype(str).tolist(), 
            processor=utils.default_process
        )

        if match and match[1] > 65: # Umbral de confianza del 65%
            nombre_p = match[0]
            fila = df[df['producto'] == nombre_p].iloc[0]
            
            p_usd = float(fila['precio_usd'])
            p_bs = p_usd * datos_tasa["tasa"]
            
            # Formateo visual (Punto para miles, coma para decimales)
            val_bs_visual = f"{p_bs:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            val_usd_visual = f"{p_usd:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

            # Formateo para voz
            texto_bs_audio = f"{p_bs:.2f}".replace(".", " con ")
            nombre_audio = nombre_p.lower().replace("mg", " miligramos").replace("ml", " mililitros")

            respuesta_voz = f"El {nombre_audio} cuesta {texto_bs_audio} Bolívares."
            
            if es_modo_admin:
                stock_val = str(fila.get('stock', '0'))
                respuesta_voz += f" Tienes {stock_val} en existencia."
            
            # Log de éxito
            supabase.table("logs_actividad").insert({
                "email": usuario_email, "accion": "CONSULTA_PRECIO", 
                "detalle": pregunta_raw, "ip_address": ip_cliente,
                "equipo_id": equipo_id, "exito": True
            }).execute()

            return jsonify({
                "exito": True,
                "producto_nombre": nombre_p,
                "p_bs": val_bs_visual,
                "p_usd": val_usd_visual,
                "respuesta": respuesta_voz,
                "modo_admin": es_modo_admin
            })

        else:
            # Log de fallo (Producto no encontrado)
            supabase.table("logs_actividad").insert({
                "email": usuario_email, "accion": "CONSULTA_PRECIO", 
                "detalle": pregunta_raw, "ip_address": ip_cliente,
                "equipo_id": equipo_id, "exito": False
            }).execute()
            return jsonify({"exito": False, "respuesta": f"Lo siento, no encontré '{pregunta_limpia}'."})

    except Exception as e:
        return jsonify({"exito": False, "respuesta": "Error procesando la búsqueda."})
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
@app.route('/admin/actualizar_tasa_maestra', methods=['POST'])
def actualizar_tasa_maestra():
    # Buscamos auth_key que viene del formulario
    auth = request.form.get('auth_key')
    
    # IMPORTANTE: Verifica que coincida con tu ADMIN_PASS
    if auth != ADMIN_PASS:
        return f"Error de autenticación: recibiste {auth}", 403

    nueva_tasa = request.form.get('tasa')
    if not nueva_tasa:
        return "Error: No se recibió ninguna tasa", 400

    try:
        tasa_val = float(str(nueva_tasa).replace(",", "."))
        
        # Usamos UPSERT para evitar errores de llave duplicada o inexistente
        supabase.table("ajustes_sistema").upsert({
            "clave": "tasa_maestra", 
            "valor": tasa_val
        }).execute()

        # Limpiamos la RAM para que todos los usuarios se actualicen
        memoria_tasa.clear()
        
        flash(f"Tasa global actualizada a {tasa_val} Bs.")
        return redirect(url_for('admin_panel', auth_key=ADMIN_PASS))

    except Exception as e:
        # Esto te dirá exactamente qué pasó en los logs de Koyeb si vuelve a fallar
        print(f"DEBUG ERROR TASA: {str(e)}")
        return f"Error interno: {str(e)}", 500
@app.route('/admin/actualizar_tasa_maestra', methods=['POST'])
def actualizar_tasa_maestra():
    # 1. Verificación de seguridad básica
    auth = request.form.get('auth_key')
    if auth != ADMIN_PASS:
        return "Acceso denegado: Clave administrativa incorrecta", 403

    nueva_tasa = request.form.get('tasa')
    
    if not nueva_tasa:
        return "Error: Debes ingresar un valor de tasa", 400

    try:
        # 2. Limpiar el formato del número (por si usan coma en vez de punto)
           tasa_val = float(str(nueva_tasa).replace(",", "."))

        # 3. Guardar en la tabla maestra de Supabase
        # Nota: Asegúrate de haber creado la tabla 'ajustes_sistema' con la clave 'tasa_maestra'
        # Cambia esto en la línea 327 aprox de tu app.py:
           supabase.table("ajustes_sistema").upsert({
           "clave": "tasa_maestra", 
           "valor": tasa_val,
           "actualizado_en": datetime.now().isoformat() # Útil para auditoría
           }).execute()

        # 4. LIMPIEZA ESTRATÉGICA DE RAM
        # Al vaciar el diccionario, obligamos a get_tasa_usuario a buscar en la DB 
        # la nueva tasa global para todos los clientes activos.
           memoria_tasa.clear()

           print(f"✅ Tasa Global actualizada a {tasa_val} por el administrador.")
           flash(f"Éxito: Tasa global actualizada a {tasa_val} Bs.")
        
           return redirect(url_for('admin_panel', auth_key=ADMIN_PASS))

    except Exception as e:
        print(f"❌ Error actualizando tasa global: {e}")
        return f"Error interno: {str(e)}", 500
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
        # 1. Obtener usuarios y tasa actual de Supabase
        usuarios_res = supabase.table("suscripciones").select("*").execute()
        usuarios = usuarios_res.data if usuarios_res.data else []
        hoy = datetime.now().date()
        
        # --- NUEVO: Obtener la Tasa Maestra actual para el panel ---
        tasa_res = supabase.table("ajustes_sistema").select("valor").eq("clave", "tasa_maestra").execute()
        tasa_val = tasa_res.data[0]['valor'] if tasa_res.data else 0.0
        # -----------------------------------------------------------

        # 2. Obtener logs (limitamos a 500 para no saturar memoria)
        logs_res = supabase.table("logs_actividad").select("*").order("created_at", desc=True).limit(500).execute()
        logs_raw = logs_res.data if logs_res.data else []

        # 3. Procesar Equipos Únicos y Resumen de Actividad
        from collections import Counter
        equipos_por_usuario = {}
        resumen_dict = {}
        logs_para_tabla = []

        for l in logs_raw:
            email = l.get('email')
            eid = l.get('equipo_id', 'D-000')
            l['fecha'] = l.get('created_at', '2026-01-01T00:00:00')
            fecha_dia = l['fecha'].split('T')[0]
            
            if email:
                if email not in equipos_por_usuario: equipos_por_usuario[email] = set()
                equipos_por_usuario[email].add(eid)
                
                if email not in resumen_dict: resumen_dict[email] = Counter()
                resumen_dict[email][fecha_dia] += 1
            
            logs_para_tabla.append(l)

        # 4. Enriquecer objeto usuarios
        for u in usuarios:
            try:
                # Usamos la lógica de 1 día de gracia mencionada en tus instrucciones
                vence = datetime.strptime(u['fecha_vencimiento'], '%Y-%m-%d').date()
                u['vencido'] = hoy > (vence + timedelta(days=1))
                u['total_equipos'] = len(equipos_por_usuario.get(u['email'], []))
            except:
                u['vencido'], u['total_equipos'] = True, 0

        # 5. Ranking de Salud del Servicio
        conteo_ranking = Counter([l['email'] for l in logs_para_tabla if l.get('email')])
        ranking = []
        for email, count in conteo_ranking.most_common(5):
            logs_cliente = [l for l in logs_para_tabla if l['email'] == email]
            exitos = len([l for l in logs_cliente if l.get('exito')])
            salud = int((exitos / len(logs_cliente)) * 100) if logs_cliente else 0
            ranking.append({"email": email, "count": count, "salud": salud, "alerta": salud < 70})

        # 6. Resumen de uso (chips)
        resumen_uso = [{"email": k, "actividad": [{"fecha": f, "cantidad": c} for f, c in sorted(v.items(), reverse=True)[:7]]} for k, v in resumen_dict.items()]

        stats = {
            "total": len(usuarios),
            "activos": len([u for u in usuarios if not u['vencido']]),
            "vencidos": len([u for u in usuarios if u['vencido']])
        }

        # RETORNO INTEGRADO CON admin.html
        return render_template('admin.html', 
                               usuarios=usuarios, 
                               stats=stats, 
                               logs=logs_para_tabla, 
                               ranking=ranking, 
                               resumen_uso=resumen_uso, 
                               admin_pass=ADMIN_PASS,
                               tasa_actual=tasa_val) # <--- Crucial para el value="{{ tasa_actual }}"
                               
    except Exception as e:
        print(f"ERROR EN PANEL ADMIN: {str(e)}")
        return f"Error interno: {str(e)}", 500
@app.route('/admin/crear', methods=['POST'])
def crear_usuario():
    auth = request.form.get('auth_key')
    if auth != ADMIN_PASS: 
        return "Error de autenticación", 403
    
    email = request.form.get('email').lower().strip()
    password_nueva = request.form.get('password')
    fecha_vence = request.form.get('vence')
    # NUEVO: Capturamos el límite de equipos del formulario (por defecto 1 si viene vacío)
    limite_equipos = request.form.get('limite_equipos', '1')
    
    try:
        # 1. Verificar si el usuario ya existe para no perder la contraseña
        res = supabase.table("suscripciones").select("*").eq("email", email).execute()
        usuario_existente = res.data[0] if res.data else None
        
        # 2. Preparar los datos
        data = {
            "email": email,
            "fecha_vencimiento": fecha_vence,
            "activo": 1,
            "limite_equipos": int(limite_equipos) # <--- NUEVO: Se guarda como entero
        }
        
        # Lógica de contraseña:
        if password_nueva and password_nueva.strip() != "":
            # Si escribiste una contraseña, se usa la nueva
            data["password"] = password_nueva
        elif usuario_existente:
            # Si no escribiste nada pero el usuario ya existe, mantenemos la vieja
            data["password"] = usuario_existente["password"]
        else:
            # Si es un usuario nuevo y no pusiste contraseña, le ponemos una por defecto
            data["password"] = "123456"

        # 3. UPSERT: Inserta si no existe, actualiza si ya existe
        supabase.table("suscripciones").upsert(data).execute()
        
        # Redirigir con éxito al panel admin
        return redirect(url_for('admin_panel', auth_key=ADMIN_PASS))

    except Exception as e:
        print(f"Error en crear/actualizar: {e}")
        return f"Error al procesar usuario: {str(e)}"
@app.route('/admin/impersonar', methods=['POST'])
def impersonar_usuario():
    auth = request.form.get('auth_key')
    if auth != ADMIN_PASS: 
        return "No autorizado", 403
    
    cliente_email = request.form.get('email')
    
    # Verificamos que el cliente exista antes de entrar
    res = supabase.table("suscripciones").select("*").eq("email", cliente_email).execute()
    
    if res.data:
        # Aquí ocurre la magia: cambiamos tu sesión por la del cliente
        session['usuario'] = cliente_email
        # Redirigimos al escritorio principal (index.html)
        return redirect('/')
    else:
        return "Cliente no encontrado", 404
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
@app.route('/admin/reset_equipos', methods=['POST'])
def reset_equipos():
    auth = request.form.get('auth_key')
    if auth != ADMIN_PASS: 
        return "Error de autenticación", 403
    
    email_cliente = request.form.get('email')
    
    try:
        # Borramos los logs de actividad de ese cliente.
        # Al borrar los logs, la cuenta de equipos únicos vuelve a cero.
        supabase.table("logs_actividad").delete().eq("email", email_cliente).execute()
        
        # Opcional: Podrías insertar un log administrativo de que se hizo el reset
        supabase.table("logs_actividad").insert({
            "email": email_cliente,
            "accion": "RESET_EQUIPOS",
            "detalle": "Administrador reseteó la lista de equipos autorizados",
            "exito": True
        }).execute()

        return redirect(url_for('admin_panel', auth_key=ADMIN_PASS))
    
    except Exception as e:
        print(f"Error al resetear equipos: {e}")
        return f"Error: {str(e)}"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))