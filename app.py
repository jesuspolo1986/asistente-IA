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
import gc # Recolector de basura
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
    usuario_email = session.get('usuario') # Asegúrate de que usas 'usuario' o 'user_email' según tu login
    if not usuario_email:
        return jsonify({"error": "No session"}), 401
    
    # Ahora get_tasa_usuario devuelve directamente el número (float)
    tasa_valor = get_tasa_usuario(usuario_email)
    
    # Devolvemos el número envuelto en el JSON que el frontend espera
    return jsonify({"tasa": tasa_valor})

def get_tasa_usuario(email):
    # Intentamos obtener la tasa 'global' de la memoria para ser rápidos
    # Pero añadimos un control de tiempo para que se refresque cada poco
    ahora = time.time()
    
    # Si la tasa no existe en RAM o pasaron más de 60 segundos, forzamos lectura de DB
    if 'global' not in memoria_tasa or (ahora - memoria_tasa.get('last_update', 0)) > 60:
        try:
            # 1. Prioridad: Tasa Maestra Global del Panel
            res = supabase.table("ajustes_sistema").select("valor").eq("clave", "tasa_maestra").execute()
            if res.data:
                nueva_tasa = float(res.data[0]['valor'])
                memoria_tasa['global'] = nueva_tasa
                memoria_tasa['last_update'] = ahora
                return nueva_tasa
        except Exception as e:
            print(f"Error consultando DB: {e}")
    
    # Si la DB falla o ya tenemos una tasa fresca en RAM, la usamos
    return memoria_tasa.get('global', obtener_tasa_real())
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
    if not session.get('logged_in'): 
        return redirect(url_for('login'))
    
    email = session.get('usuario')
    
    # 1. Obtenemos el valor numérico (ej: 555.0)
    tasa_valor = get_tasa_usuario(email)
    
    dias_restantes = 0
    if session.get('fecha_vencimiento'):
        try:
            vence = datetime.strptime(session['fecha_vencimiento'], '%Y-%m-%d').date()
            dias_restantes = (vence - datetime.now().date()).days
        except: 
            pass
    
    # CORRECCIÓN AQUÍ: Pasamos 'tasa_valor' directamente sin ['tasa']
    return render_template('index.html', 
                           tasa=tasa_valor, 
                           dias_restantes=dias_restantes, 
                           email=email)

# --- LÓGICA DE ELENA (BÚSQUEDA EN BASE DE DATOS) ---
@app.route('/preguntar', methods=['POST'])
def preguntar():
    import gc
    import random
    data = request.get_json()
    usuario_email = session.get('usuario')
    
    if not usuario_email: 
        return jsonify({"respuesta": "Sesión expirada."}), 401
    
    pregunta_raw = data.get('pregunta', '').lower().strip()
    
    # --- 1. PRIORIDAD: MODO GERENCIA ---
    if "activar modo gerencia" in pregunta_raw or "modo gerencia" in pregunta_raw:
        return jsonify({
            "exito": True,
            "respuesta": "Modo gerencia activado. Ahora puedes ver el stock y cambiar la tasa.",
            "modo_admin": True,
            "producto_nombre": "GERENCIA",
            "p_bs": "---",
            "p_usd": "---"
        })

    # --- 2. DATOS DE CONTEXTO ---
    equipo_id = data.get('equipo_id', 'DESCONOCIDO')
    es_modo_admin = data.get('modo_admin', False)
    tasa_actual = get_tasa_usuario(usuario_email)

    # --- 3. CAMBIO DE TASA ---
    if data.get('nueva_tasa'):
        try:
            val = float(str(data.get('nueva_tasa')).replace(",", "."))
            supabase.table("suscripciones").update({"tasa_personalizada": val}).eq("email", usuario_email).execute()
            memoria_tasa['global'] = val 
            return jsonify({"respuesta": f"Tasa actualizada a {val} Bs.", "exito_tasa": True, "tasa": val})
        except: return jsonify({"respuesta": "Formato de tasa no válido."})

    # --- 4. BÚSQUEDA EN INVENTARIO ---
    try:
        res = supabase.table("inventarios").select("producto, precio_usd, stock").eq("empresa_email", usuario_email).execute()
        inventario = res.data
        del res
        
        if not inventario:
            return jsonify({"respuesta": "Elena: Tu inventario está vacío."})

        # --- LIMPIEZA DE RUIDO MEJORADA ---
        pregunta_limpia = pregunta_raw
        frases_ruido = [
            "cuanto cuesta el", "cuanto cuesta la", "cuanto cuesta",
            "cuanto vale el", "cuanto vale la", "cuanto vale",
            "que precio tiene el", "que precio tiene la", "que precio tiene",
            "dame el precio de", "dame el precio del", "dame el precio",
            "precio del", "precio de la", "precio de", "precio",
            "en cuanto sale el", "en cuanto sale la", "en cuanto sale",
            "tendras", "tienes", "busco", "necesito"
        ]
        
        for f in frases_ruido:
            pregunta_limpia = pregunta_limpia.replace(f, "")
        
        pregunta_limpia = pregunta_limpia.replace("?", "").replace("¿", "").strip()

        if not pregunta_limpia:
            return jsonify({"exito": False, "respuesta": "¿Qué producto deseas consultar?"})

        # --- EJECUCIÓN DE BÚSQUEDA (CORREGIDO) ---
        nombres = [str(i['producto']) for i in inventario]
        match = process.extractOne(pregunta_limpia, nombres, processor=utils.default_process)

        if match and match[1] > 65:
            nombre_p = match[0]
            item = next((i for i in inventario if i['producto'] == nombre_p), None)
            
            if item:
                p_usd = float(item['precio_usd'])
                p_bs = round(p_usd * tasa_actual, 2) 
                
                v_bs_vis = f"{p_bs:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                txt_audio = f"{p_bs:.2f}".replace(".", " con ")

                saludos = [
                    f"¡Hola! Con mucho gusto te informo que el {nombre_p.lower()} tiene un costo de",
                    f"Un placer atenderte. El {nombre_p.lower()} que buscas está en",
                    f"Para servirte, te indico que el precio del {nombre_p.lower()} es de",
                    f"¡Buen día! El valor actual para el {nombre_p.lower()} es de",
                    f"Es un gusto saludarte. Te confirmo que el {nombre_p.lower()} cuesta",
                    f"Te informo que el {nombre_p.lower()} tiene un precio de",
                    f"El {nombre_p.lower()} se encuentra disponible por",
                    f"Actualmente el costo del {nombre_p.lower()} es de",
                    f"Sí, el precio registrado para el {nombre_p.lower()} es",
                    f"El valor de mercado para el {nombre_p.lower()} hoy es",
                    f"¡Buenas noticias! Contamos con {nombre_p.lower()} y su precio es",
                    f"Claro que sí, el {nombre_p.lower()} lo tenemos en",
                    f"Por supuesto, el precio actualizado del {nombre_p.lower()} es de",
                    f"Contamos con existencia de {nombre_p.lower()} a un valor de",
                    f"¡Confirmado! El {nombre_p.lower()} tiene un costo de",
                    f"Según nuestro inventario, el {nombre_p.lower()} cuesta",
                    f"Te indico que el precio actualizado para el {nombre_p.lower()} es",
                    f"El {nombre_p.lower()} está disponible actualmente por",
                    f"He verificado y el {nombre_p.lower()} tiene un precio de",
                    f"Para tu referencia, el costo del {nombre_p.lower()} es de"
                ]
                
                inicio_frase = random.choice(saludos)
                respuesta_texto = f"{inicio_frase} {txt_audio} Bolívares."
                
                if es_modo_admin:
                    stock_actual = item.get('stock', 0)
                    respuesta_texto += f" Hay {stock_actual} unidades en existencia."

                supabase.table("logs_actividad").insert({
                    "email": usuario_email, "accion": "CONSULTA", 
                    "equipo_id": equipo_id, "exito": True
                }).execute()

                del inventario
                gc.collect()

                return jsonify({
                    "exito": True, 
                    "producto_nombre": nombre_p, 
                    "p_bs": v_bs_vis,
                    "p_usd": f"{p_usd:,.2f}",
                    "respuesta": respuesta_texto, 
                    "modo_admin": es_modo_admin
                })

        # Si no hubo coincidencia
        del inventario
        gc.collect()
        return jsonify({"exito": False, "respuesta": f"Lo siento, no encontré el producto '{pregunta_limpia}'."})

    except Exception as e:
        gc.collect()
        return jsonify({"exito": False, "respuesta": "Error procesando la búsqueda."})
@app.route('/upload', methods=['POST'])
def upload_file():
    usuario_email = session.get('usuario')
    if not usuario_email: 
        return jsonify({"success": False, "error": "No login"}), 401
    
    file = request.files.get('archivo')
    if not file: 
        return jsonify({"success": False, "error": "No file"})

    try:
        # 1. Leer Excel
        df = pd.read_excel(file)
        
        # Búsqueda inteligente de cabeceras si hay basura arriba
        if not any(x in str(df.columns).lower() for x in ['producto', 'precio', 'articulo']):
            file.seek(0) # Resetear puntero del archivo para volver a leer
            for i in range(10):
                df = pd.read_excel(file, skiprows=i+1)
                if any(x in str(df.columns).lower() for x in ['producto', 'precio', 'articulo']):
                    break

        # 2. Encontrar columnas automáticamente
        cols_encontradas = encontrar_columnas_maestras(df.columns)
        
        if 'producto' not in cols_encontradas or 'precio' not in cols_encontradas:
            return jsonify({"success": False, "error": "No detecto columnas de Producto o Precio"})

        # 3. Limpiar y Estandarizar Datos (Protección contra errores de escritura)
        df_limpio = pd.DataFrame()
        
        # Limpiar Nombres: Quitar filas vacías de productos
        df_limpio['producto'] = df[cols_encontradas['producto']].astype(str).str.upper().str.strip()
        df_limpio = df_limpio[df_limpio['producto'] != 'NAN'] # Eliminar filas vacías

        # Limpiar Precios: Usar la función limpiar_precio que ya tienes
        df_limpio['precio_usd'] = df[cols_encontradas['precio']].apply(limpiar_precio)
        
        # --- CORRECCIÓN CRÍTICA PARA EL STOCK ---
        def limpiar_stock(val):
            try:
                if pd.isna(val) or str(val).strip() in ['...', '', 'None']:
                    return 0
                # Convertir a float primero (por si viene 10.0) y luego a int
                return int(float(str(val).replace(',', '.')))
            except:
                return 0

        if 'stock' in cols_encontradas:
            df_limpio['stock'] = df[cols_encontradas['stock']].apply(limpiar_stock)
        else:
            df_limpio['stock'] = 0

        df_limpio['empresa_email'] = usuario_email

        # 4. Guardar en Supabase
        # Borramos lo anterior del usuario
        supabase.table("inventarios").delete().eq("empresa_email", usuario_email).execute()
        
        # Subida por bloques (Chunks) para estabilidad
        datos_finales = df_limpio.to_dict(orient='records')
        for i in range(0, len(datos_finales), 100):
            supabase.table("inventarios").insert(datos_finales[i:i+100]).execute()

        # Limpieza manual de memoria
        import gc
        del df
        del df_limpio
        gc.collect()

        return jsonify({"success": True, "productos": len(datos_finales)})

    except Exception as e:
        print(f"Error en carga: {str(e)}")
        return jsonify({"success": False, "error": str(e)})
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