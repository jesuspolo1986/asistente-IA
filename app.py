import os
import time
import json
import base64
import gc
import re
import unicodedata
import random
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
import pandas as pd
from supabase import create_client, Client
from groq import Groq
from rapidfuzz import process, utils

app = Flask(__name__)
app.secret_key = 'elena_farmacia_2026_key'

# Inicialización de Groq (Asegúrate de tener la variable en Koyeb)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
groq_client = Groq(api_key=GROQ_API_KEY)
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
from rapidfuzz import process, fuzz, utils

def buscar_producto_excel(nombre_medicamento, email_usuario):
    try:
        # 1. Traemos el inventario filtrado por email
        res = supabase.table("inventarios")\
            .select("producto, precio_usd, stock")\
            .eq("empresa_email", email_usuario)\
            .execute()
        
        inventario = res.data
        
        if not inventario:
            print(f"Búsqueda: Inventario no encontrado para {email_usuario}")
            return {"encontrado": False, "error": "Inventario vacío"}

        if not nombre_medicamento:
            return {"encontrado": False, "error": "Nombre de medicamento vacío"}

        # --- MEJORA CRÍTICA: Estandarización a minúsculas ---
        # Creamos una lista de nombres limpia para la IA
        # Guardamos el original en un diccionario para recuperarlo luego
        nombres_para_busqueda = {
            str(i['producto']).strip().lower(): i 
            for i in inventario if i.get('producto')
        }
        
        lista_nombres = list(nombres_para_busqueda.keys())
        query_usuario = str(nombre_medicamento).strip().lower()

        # 2. Buscamos la mejor coincidencia con RapidFuzz
        # fuzz.partial_ratio es mejor para casos como "vitamina c" vs "VITAMINA C 1G"
        match = process.extractOne(
            query_usuario, 
            lista_nombres, 
            score_cutoff=60, 
            processor=utils.default_process,
            scorer=fuzz.partial_ratio # Busca la coincidencia parcial (mejor para récipes)
        )
        
        if match:
            nombre_minimo = match[0]
            puntuacion = match[1]
            
            # Recuperamos el item original (con sus mayúsculas y datos)
            item = nombres_para_busqueda[nombre_minimo]
            
            # Aseguramos tipos de datos correctos
            precio = float(item.get('precio_usd', 0) or 0)
            nombre_original = str(item.get('producto'))
            
            print(f"✅ Match encontrado: {nombre_original} (Similitud: {puntuacion}%)")
            
            return {
                "encontrado": True,
                "nombre": nombre_original,
                "precio": precio,
                "stock": item.get('stock', 0),
                "score": puntuacion
            }
        
        print(f"❌ No se encontró coincidencia cercana para: {nombre_medicamento}")
        return {"encontrado": False}

    except Exception as e:
        print(f"🔥 Error crítico en búsqueda de inventario: {str(e)}")
        return {"encontrado": False, "error": str(e)}
# 1. Asegúrate de que el nombre aquí sea 'procesar_vision_groq'
def formatear_respuesta_farmacia(producto_data, tasa):
    nombre = producto_data['nombre']
    precio_usd = producto_data['precio']
    stock = producto_data['stock']
    
    precio_bs = precio_usd * tasa
    # Convertimos 768.80 en "768 con 80" para que el audio sea natural
    txt_audio_bs = f"{precio_bs:.2f}".replace(".", " con ")
    
    return (f"¡Claro! He encontrado {nombre}. "
            f"Tiene un precio de {precio_usd} dólares, que al cambio son {txt_audio_bs} bolívares. "
            f"Nos quedan {stock} unidades disponibles.")
def procesar_vision_groq(image_path):
    import base64
    import json
    
    try:
        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')

        # Usamos un prompt más directo y quitamos el modo JSON estricto de Groq
        # para que no nos devuelva un error vacío si se confunde
        completion = groq_client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[{
                "role": "user",
                "content": [
                 {"type": "text", "text": "Identify the medicine name in this image. Even if the handwriting is bad or misspelled, provide the most likely correct commercial or generic name. Respond only with the name."},
                 {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ]
            }],
            temperature=0.0 # Cero para máxima precisión
        )

        respuesta_raw = completion.choices[0].message.content
        print(f"DEBUG IA LEYÓ: {respuesta_raw}") # ESTO APARECERÁ EN TUS LOGS DE KOYEB

        # Intentamos limpiar por si la IA se pone habladora
        medicamento = respuesta_raw.replace('"', '').replace('{', '').replace('}', '').strip()
        
        # Si la respuesta es muy larga, tomamos solo la primera línea
        medicamento = medicamento.split('\n')[0]
        
        return medicamento

    except Exception as e:
        print(f"ERROR CRÍTICO EN VISIÓN: {str(e)}")
        return "Error de lectura"
@app.route('/analizar_recipe', methods=['POST'])
def api_analizar_recipe():
    usuario_id = session.get('usuario', 'invitado')
    tasa_actual = get_tasa_usuario(usuario_id) # Obtenemos la tasa real del usuario
    
    if 'foto' not in request.files:
        return jsonify({"error": "No se recibió imagen"}), 400
    
    foto = request.files['foto']
    path = os.path.join('/tmp', f"scan_{int(time.time())}.jpg")
    foto.save(path)
    
    try:
        medicamento_detectado = procesar_vision_groq(path) 
        resultado_busqueda = buscar_producto_excel(medicamento_detectado, usuario_id)
        
        if os.path.exists(path): os.remove(path)

        if resultado_busqueda.get("encontrado"):
            # UNIFICACIÓN: Generamos el mismo mensaje que la voz
            mensaje_voz = formatear_respuesta_farmacia(resultado_busqueda, tasa_actual)
            
            return jsonify({
                "lectura_ia": {"nombre_del_medicamento": medicamento_detectado},
                "inventario": resultado_busqueda,
                "respuesta": mensaje_voz # <--- EL FRONTEND DEBE LEER ESTO
            })
        else:
            return jsonify({
                "lectura_ia": {"nombre_del_medicamento": medicamento_detectado},
                "respuesta": f"Lo siento, leí {medicamento_detectado} pero no está en el inventario."
            })

    except Exception as e:
        if os.path.exists(path): os.remove(path)
        return jsonify({"error": str(e)}), 500
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # 0. DEFINIR FECHA ACTUAL (Crítico para que funcione la validación)
        hoy = datetime.now().date()
        
        email = request.form.get('email', '').lower().strip()
        password = request.form.get('password')
        # Capturamos el ID único generado por el script en login.html
        current_device_id = request.form.get('device_id', 'unknown_device')
        
        # Buscamos al usuario en Supabase
        res = supabase.table("suscripciones").select("*").eq("email", email).execute()
        
        if res.data:
            user = res.data[0]
            
            # 1. VERIFICACIÓN DE CREDENCIALES Y ESTADO
            if user.get('password') == password and user.get('activo') == 1:
                
                # 2. BLOQUEO POR FECHA (INCLUYE 1 DÍA DE GRACIA REAL)
                try:
                    fecha_vence = datetime.strptime(user['fecha_vencimiento'], '%Y-%m-%d').date()
                    
                    # El límite de gracia es el día siguiente al vencimiento
                    limite_gracia = fecha_vence + timedelta(days=1)
                    
                    # Bloqueo estricto: Si hoy ya pasó el día de gracia
                    if hoy > limite_gracia:
                        return render_template('login.html', error=f"Suscripción expirada el {fecha_vence}. Contacte soporte.")
                    
                    # LÓGICA DE BANNER: Si hoy es exactamente el día después del vencimiento
                    if hoy == limite_gracia:
                        session['aviso_gracia'] = f"Tu suscripción expiró ayer ({fecha_vence}). Tienes un día de gracia para renovar."
                    else:
                        session['aviso_gracia'] = None

                except Exception as e:
                    print(f"Error validando fecha: {e}")
                    # En caso de error, dejamos pasar por seguridad de servicio, pero logueamos
                    session['aviso_gracia'] = None

                # 3. BLOQUEO POR LÍMITE DE EQUIPOS SEGÚN PLAN
                logs_res = supabase.table("logs_actividad")\
                    .select("detalle")\
                    .eq("email", email)\
                    .eq("accion", "LOGIN")\
                    .execute()
                
                equipos_registrados = set()
                if logs_res.data:
                    for log in logs_res.data:
                        if "ID:" in log['detalle']:
                            try:
                                d_id = log['detalle'].split("ID:")[1].strip()
                                equipos_registrados.add(d_id)
                            except IndexError:
                                continue
                
                # Obtiene el límite de la DB o usa 1 por defecto
                limite_permitido = user.get('limite_equipos', 1) 

                if current_device_id not in equipos_registrados:
                    if len(equipos_registrados) >= limite_permitido:
                        return render_template('login.html', 
                            error=f"Acceso denegado: Su plan actual permite {limite_permitido} equipo(s).")

                # 4. REGISTRO DE ACCESO EXITOSO Y CREACIÓN DE SESIÓN
                supabase.table("logs_actividad").insert({
                    "email": email,
                    "accion": "LOGIN",
                    "detalle": f"Ingreso desde ID: {current_device_id}",
                    "exito": True
                }).execute()

                # Limpieza de basura para ahorrar memoria en el servidor
                gc.collect()

                session.permanent = True
                session['logged_in'] = True
                session['usuario'] = email
                session['device_id'] = current_device_id
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
    import re
    import unicodedata
    from rapidfuzz import process, utils

    data = request.get_json()
    usuario_email = session.get('usuario')
    
    if not usuario_email: 
        return jsonify({"respuesta": "Sesión expirada."}), 401
    
    pregunta_raw = data.get('pregunta', '').lower().strip()

    # --- FUNCIÓN INTERNA PARA QUITAR TILDES ---
    def eliminar_tildes(texto):
        return ''.join(c for c in unicodedata.normalize('NFD', texto)
                      if unicodedata.category(c) != 'Mn')

    # --- 1. PRIORIDAD: MODO GERENCIA ---
    pregunta_sin_tildes = eliminar_tildes(pregunta_raw)
    if "activar modo gerencia" in pregunta_sin_tildes or "modo gerencia" in pregunta_sin_tildes:
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
        
        if not inventario:
            return jsonify({"respuesta": "Elena: Tu inventario está vacío."})

        # --- LIMPIEZA DE RUIDO PROFESIONAL (REGEX) ---
        # 1. Quitamos tildes para que "cuánto" sea "cuanto"
        limpia = eliminar_tildes(pregunta_raw)
        
        # 2. Lista de frases de ruido que Elena debe ignorar
        # Usamos \b para asegurar que borre palabras completas y no partes de nombres
        frases_ruido = [
            r"cuanto cuesta el", r"cuanto cuesta la", r"cuanto cuesta",
            r"cuanto vale el", r"cuanto vale la", r"cuanto vale",
            r"que precio tiene el", r"que precio tiene la", r"que precio tiene",
            r"dame el precio de", r"dame el precio del", r"dame el precio",
            r"precio del", r"precio de la", r"precio de", r"precio",
            r"en cuanto sale el", r"en cuanto sale la", r"en cuanto sale",
            r"que tiene", r"tienes", r"tendras", r"busco", r"necesito",
            r"\bla\b", r"\bel\b", r"\bdame\b"
        ]
        
        for f in frases_ruido:
            limpia = re.sub(f, "", limpia).strip()
        
        # 3. Quitamos signos y espacios extra
        limpia = limpia.replace("?", "").replace("¿", "").strip()

        # Si queda vacía por error, volvemos a la original para no fallar
        if not limpia:
            limpia = pregunta_raw

        # --- EJECUCIÓN DE BÚSQUEDA ---
        nombres = [str(i['producto']) for i in inventario]
        match = process.extractOne(limpia, nombres, processor=utils.default_process)

        if match and match[1] > 45: # Bajamos a 60 para mayor flexibilidad
            nombre_p = match[0]
            item = next((i for i in inventario if i['producto'] == nombre_p), None)
            
            if item:
                p_usd = float(item['precio_usd'])
                p_bs = round(p_usd * tasa_actual, 2) 
                v_bs_vis = f"{p_bs:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                txt_audio = f"{p_bs:.2f}".replace(".", " con ")

                # --- GENERADOR DE SALUDOS DINÁMICOS (Más de 50 combinaciones) ---
                saludos_inicio = [
                    "¡Hola!", "¡Buen día!", "¡Saludos!", "Es un gusto saludarte.", "Un placer atenderte.", 
                    "Hola, ¿cómo estás?", "¡Feliz día!", "Qué bueno que nos consultas.", "Bienvenido.",
                    "Es un placer servirte.", "Estamos para ayudarte.", "Gracias por preguntar.",
                    "¡Hola! Qué gusto.", "Buen día, gracias por consultarnos.", "Hola, un placer."
                ]
                
                acciones = [
                    f"te informo que el {nombre_p.lower()}", f"el precio del {nombre_p.lower()}", 
                    f"el {nombre_p.lower()} que buscas", f"te confirmo que el {nombre_p.lower()}",
                    f"actualmente el {nombre_p.lower()}", f"el valor del {nombre_p.lower()}",
                    f"el costo de el {nombre_p.lower()}", f"la cotización para el {nombre_p.lower()}",
                    f"según nuestro sistema el {nombre_p.lower()}", f"te indico que el {nombre_p.lower()}"
                ]
                
                conectores = [
                    "tiene un costo de", "está en", "se encuentra en", "cuesta", "sale en", 
                    "lo tenemos por el valor de", "está disponible por", "tiene un precio de",
                    "está marcado en", "está cotizado en", "se ubica en"
                ]

                # Esta línea genera la magia mezclando las 3 listas
                inicio_frase = f"{random.choice(saludos_inicio)} {random.choice(acciones)} {random.choice(conectores)}"
                
                respuesta_texto = f"{inicio_frase} {txt_audio} Bolívares."
                
                
                
                if es_modo_admin:
                    stock_actual = item.get('stock', 0)
                    respuesta_texto += f" Hay {stock_actual} unidades en existencia."

                # Registro y limpieza
                supabase.table("logs_actividad").insert({
                    "email": usuario_email,"detalle": pregunta_raw, "accion": "CONSULTA", 
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
        return jsonify({"exito": False, "respuesta": f"Lo siento, no encontré el producto '{limpia}'."})

    except Exception as e:
        gc.collect()
        return jsonify({"exito": False, "respuesta": f"Error: {str(e)}"})
@app.route('/upload', methods=['POST'])
def upload_file():
    usuario_email = session.get('usuario')
    if not usuario_email: 
        return jsonify({"success": False, "error": "No login"}), 401
    
    file = request.files.get('archivo')
    if not file: 
        return jsonify({"success": False, "error": "No file"})

    nombre_archivo = file.filename.lower()

    try:
        # --- MEJORA 1: Soporte para CSV y Excel ---
        def leer_segun_tipo(f, saltar=0):
            f.seek(0) # Siempre resetear antes de leer
            if nombre_archivo.endswith('.csv'):
                return pd.read_csv(f, skiprows=saltar)
            else:
                return pd.read_excel(f, skiprows=saltar)

        # Intento inicial
        df = leer_segun_tipo(file)
        
        # Búsqueda inteligente de cabeceras (Tu lógica original mejorada)
        cabeceras_validas = ['producto', 'precio', 'articulo', 'nombre']
        if not any(x in str(df.columns).lower() for x in cabeceras_validas):
            encontrado = False
            for i in range(1, 11): # Probar saltando de 1 a 10 filas
                df = leer_segun_tipo(file, saltar=i)
                if any(x in str(df.columns).lower() for x in cabeceras_validas):
                    encontrado = True
                    break
            if not encontrado:
                return jsonify({"success": False, "error": "No se encontraron cabeceras válidas en las primeras 10 filas"})

        # --- El resto de tu lógica de limpieza de columnas ---
        cols_encontradas = encontrar_columnas_maestras(df.columns)
        
        # ... (Tu código de limpieza de stock y precios está perfecto) ...

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
        
        # Obtener la Tasa Maestra actual
        tasa_res = supabase.table("ajustes_sistema").select("valor").eq("clave", "tasa_maestra").execute()
        tasa_val = tasa_res.data[0]['valor'] if tasa_res.data else 0.0

        # 2. Obtener logs (limitamos a 500 para proteger la RAM de 1GB)
        logs_res = supabase.table("logs_actividad").select("*").order("created_at", desc=True).limit(500).execute()
        logs_raw = logs_res.data if logs_res.data else []

        # 3. Procesar datos
        from collections import Counter
        equipos_por_usuario = {}
        resumen_dict = {}
        logs_para_tabla = []

        for l in logs_raw:
            email = l.get('email')
            eid = l.get('equipo_id', 'D-000')
            
            # Formateo de fecha
            raw_fecha = l.get('fecha') or l.get('created_at')
            try:
                dt = datetime.fromisoformat(str(raw_fecha).replace('Z', '+00:00'))
                l['fecha_bonita'] = dt.strftime('%d %b, %I:%M %p')
                fecha_dia = dt.strftime('%Y-%m-%d')
            except:
                l['fecha_bonita'] = str(raw_fecha)
                fecha_dia = str(raw_fecha).split('T')[0]
            
            if email:
                # Contar equipos únicos
                if email not in equipos_por_usuario: equipos_por_usuario[email] = set()
                equipos_por_usuario[email].add(eid)
                
                # Agrupar para el gráfico de barras
                if email not in resumen_dict: resumen_dict[email] = Counter()
                resumen_dict[email][fecha_dia] += 1
            
            logs_para_tabla.append(l)

        # 4. Generar Resumen de Uso (PARA LAS TARJETAS VISUALES)
        resumen_uso = []
        for email, conteos in resumen_dict.items():
            # Tomamos los últimos 7 días con actividad
            dias_ordenados = [{"fecha": f, "cantidad": c} for f, c in sorted(conteos.items(), reverse=True)[:7]]
            total_semana = sum(c for f, c in conteos.items())
            resumen_uso.append({
                "email": email, 
                "actividad": dias_ordenados,
                "total_semana": total_semana
            })

        # 5. Enriquecer objeto usuarios con Lógica de Gracia
        for u in usuarios:
            try:
                vence = datetime.strptime(u['fecha_vencimiento'], '%Y-%m-%d').date()
                # Aplicamos el día de gracia: vence hoy, pero entra mañana
                u['vencido'] = hoy > (vence + timedelta(days=1))
                u['total_equipos'] = len(equipos_por_usuario.get(u['email'], []))
            except:
                u['vencido'], u['total_equipos'] = True, 0

        # 6. Ranking de Salud (Detectar fallos)
        conteo_ranking = Counter([l['email'] for l in logs_para_tabla if l.get('email')])
        ranking = []
        for email, count in conteo_ranking.most_common(5):
            logs_cliente = [l for l in logs_para_tabla if l['email'] == email]
            exitos = len([l for l in logs_cliente if l.get('exito')])
            salud = int((exitos / len(logs_cliente)) * 100) if logs_cliente else 0
            ranking.append({"email": email, "count": count, "salud": salud, "alerta": salud < 70})

        stats = {
            "total": len(usuarios),
            "activos": len([u for u in usuarios if not u['vencido']]),
            "vencidos": len([u for u in usuarios if u['vencido']])
        }

        # Liberar memoria explícitamente antes de renderizar (Buena práctica en Koyeb)
        gc.collect()

        return render_template('admin.html', 
                               usuarios=usuarios, 
                               stats=stats, 
                               logs=logs_para_tabla, 
                               ranking=ranking, 
                               resumen_uso=resumen_uso, 
                               admin_pass=ADMIN_PASS,
                               tasa_actual=tasa_val)
                               
    except Exception as e:
        print(f"⚠️ ERROR CRÍTICO EN PANEL ADMIN: {str(e)}")
        return f"Error en el servidor: {str(e)}", 500
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
# --- LÓGICA DE BLOQUEO POR EQUIPO ---

def verificar_limite_equipos(email, plan_tipo, current_device_id):
    # Definir límites según el plan
    limite = 1 if plan_tipo == "basico" else 3 # Ejemplo: básico 1, premium 3
    
    # Consultar cuántos equipos distintos ha usado este email
    res = supabase.table("logs_actividad")\
        .select("detalle")\
        .eq("email", email)\
        .eq("accion", "LOGIN")\
        .execute()
    
    # Extraer IDs de dispositivos únicos de los logs
    equipos_registrados = set()
    for log in res.data:
        # Asumiendo que guardamos el ID en el campo detalle o tenemos un campo específico
        if 'ID:' in log['detalle']:
            device_id = log['detalle'].split('ID:')[1].strip()
            equipos_registrados.add(device_id)
    
    # Si el equipo actual es nuevo y ya alcanzó el límite
    if current_device_id not in equipos_registrados and len(equipos_registrados) >= limite:
        return False # Bloquear acceso
    return True # Permitir acceso


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