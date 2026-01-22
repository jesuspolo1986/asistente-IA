from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
import pandas as pd
import os
import io
from pyDolarVenezuela.pages import AlCambio
from pyDolarVenezuela import Monitor
from datetime import datetime, timedelta
from supabase import create_client, Client

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
@app.route('/admin')
def admin_panel():
    auth = request.args.get('auth_key')
    if auth != ADMIN_PASS: return "Acceso Denegado", 403
    
    # 1. Buscamos los usuarios en Supabase
    res = supabase.table("suscripciones").select("*").execute()
    usuarios = res.data
    
    # 2. Calculamos las estadísticas para llenar los {{ stats }}
    hoy = datetime.now().date()
    stats = {"activos": 0, "vencidos": 0, "total": len(usuarios)}
    
    for u in usuarios:
        vence = datetime.strptime(u['fecha_vencimiento'], '%Y-%m-%d').date()
        u['vencido'] = vence < hoy
        if u['vencido']: stats["vencidos"] += 1
        else: stats["activos"] += 1
        
    # 3. ENVIAMOS los datos al HTML
    return render_template('admin.html', usuarios=usuarios, stats=stats, admin_pass=ADMIN_PASS)
from rapidfuzz import process, utils

@app.route('/preguntar', methods=['POST'])
def preguntar():
    data = request.get_json()
    
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

    # 4. LIMPIEZA AVANZADA: Quitamos frases comunes para dejar solo el "núcleo" del producto
    palabras_ruido = ["cuanto cuesta", "cuanto vale", "que precio tiene", "precio de", "dame el precio", "tienes", "busco", "valor"]
    pregunta_limpia = pregunta_raw
    for frase in palabras_ruido:
        pregunta_limpia = pregunta_limpia.replace(frase, "")
    pregunta_limpia = pregunta_limpia.strip()

    tasa = inventario_memoria["tasa"]

    try:
        # 5. BÚSQUEDA DIFUZA (Fuzzy Search)
        # Extraemos las mejores coincidencias (score > 60 para evitar errores locos)
        resultados = process.extract(
            pregunta_limpia, 
            df['Producto'].astype(str).tolist(), 
            limit=5, 
            processor=utils.default_process
        )
        
        # Filtramos resultados que tengan buena similitud
        matches_validos = [r for r in resultados if r[1] > 60]

        if not matches_validos:
            return jsonify({"respuesta": f"Lo siento, no logré encontrar '{pregunta_limpia}' en el inventario."})

        # CASO 1: Una coincidencia muy clara (Similitud mayor a 90)
        if len(matches_validos) == 1 or matches_validos[0][1] > 90:
            nombre_match = matches_validos[0][0]
            fila = df[df['Producto'] == nombre_match].iloc[0]
            
            p_usd = float(fila['Precio_USD'])
            p_bs = p_usd * tasa
            stock = fila['Stock'] if 'Stock' in fila.columns else "?"
            
            res = f"El {nombre_match} cuesta {p_usd:,.2f} dólares, que al cambio son {p_bs:,.2f} bolívares. Quedan {stock} unidades."
            return jsonify({"respuesta": res})

        # CASO 2: Varias presentaciones similares (Ej: "Atamel")
        else:
            opciones = []
            for m in matches_validos[:3]: # Limitamos a 3 para la voz de Elena
                nombre_p = m[0]
                f_p = df[df['Producto'] == nombre_p].iloc[0]
                u_p = float(f_p['Precio_USD'])
                b_p = u_p * tasa
                opciones.append(f"{nombre_p} en {u_p}$ ({b_p:,.2f} Bs)")
            
            texto_opciones = " . también tengo . ".join(opciones)
            return jsonify({"respuesta": f"Encontré varias opciones: {texto_opciones}. ¿Cuál de ellas necesitas?"})

    except Exception as e:
        return jsonify({"respuesta": f"Error en la búsqueda: {str(e)}"})
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