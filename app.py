import os
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Necesario para entornos de servidor (Koyeb/Heroku)
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, send_file
from sqlalchemy import create_engine, text
from werkzeug.utils import secure_filename # Import único
from mistralai import Mistral
from fpdf import FPDF
import io
from fpdf.enums import XPos, YPos
from datetime import datetime, date, timedelta
from supabase import create_client
from rapidfuzz import process, utils # Asegúrate de tenerlo instalado

app = Flask(__name__)

# --- CONFIGURACIÓN DE SEGURIDAD ---
app.secret_key = os.environ.get("FLASK_SECRET", "analista_pro_2026_top_secret")
app.config['UPLOAD_FOLDER'] = 'uploads'

# --- CONFIGURACIÓN DE SERVICIOS (BD & IA) ---
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:aSxRZ3rVrMu2Oasu@db.kebpamfydhnxeaeegulx.supabase.co:6543/postgres")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "p2KCokd08zRypMAZQxMbC4ImxkM5DPK1")

# Inicialización de Clientes
engine = create_engine(DATABASE_URL)
client = Mistral(api_key=MISTRAL_API_KEY)

# Supabase con validación de seguridad
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    print("⚠️ ADVERTENCIA: SUPABASE_URL o KEY no configuradas. El sistema de créditos podría fallar.")

# Memoria global para Elena AI
inventario_global = {"df": None, "tasa": 36.50}
# ==========================================================
# BLOQUE DE INTEGRACIÓN: ELENA AI (COPIAR DESDE AQUÍ)
# ==========================================================
from rapidfuzz import process, utils

# Memoria global para Elena
inventario_global = {"df": None, "tasa": 36.50}

# Mapeo para que Elena encuentre las columnas sin importar el nombre en el Excel
MAPEO_ELENA = {
    'Producto': ['producto', 'descripcion', 'nombre', 'articulo', 'item'],
    'Precio Venta': ['precio venta', 'pvp', 'precio', 'venta', 'precio_unitario'],
    'Costo': ['costo', 'compra', 'p.costo'],
    'Stock Actual': ['stock actual', 'stock', 'cantidad', 'existencia']
}

@app.route('/preguntar', methods=['POST'])
def preguntar():
    """Ruta de Elena para búsqueda rápida de precios y stock"""
    data = request.json
    pregunta = data.get("pregunta", "").lower().strip()
    modo_admin = data.get("modo_admin", False)
    
    if inventario_global["df"] is None:
        return jsonify({"respuesta": "Elena: Aún no he recibido el reporte de inventario."})

    df = inventario_global["df"]
    
    # Limpiamos la pregunta para mejorar la búsqueda
    termino = pregunta.replace("precio", "").replace("cuanto cuesta", "").replace("tienes", "").strip()
    
    # Búsqueda difusa (Elena busca aunque el usuario escriba con errores)
    match = process.extractOne(termino, df['Producto'].astype(str).tolist(), processor=utils.default_process)

    if match and match[1] > 65:
        fila = df[df['Producto'] == match[0]].iloc[0]
        p_usd = float(fila['Precio Venta'])
        p_bs = p_usd * inventario_global["tasa"]
        
        if modo_admin:
            # Info detallada para el dueño
            costo = float(fila.get('Costo', 0))
            margen = ((p_usd - costo) / p_usd) * 100 if p_usd > 0 else 0
            res = f"📊 {match[0]} | Stock: {int(fila.get('Stock Actual', 0))} | PVP: ${p_usd:.2f} | Margen: {margen:.1f}%"
        else:
            # Info sencilla para el cliente (con conversión a bolívares)
            res = f"El {match[0]} tiene un costo de {p_bs:,.2f} Bs (son {p_usd:,.2f} dólares)."
        
        return jsonify({"respuesta": res, "tasa_sync": inventario_global["tasa"]})

    return jsonify({"respuesta": "No logré encontrar ese producto. ¿Podrías ser más específico?"})

# MODIFICACIÓN NECESARIA EN TU FUNCIÓN UPLOAD EXISTENTE:
# Dentro de tu ruta @app.route('/upload'), DESPUÉS de crear el 'df', 
# debes añadir estas líneas para que Elena sepa leerlo:
def sincronizar_con_elena(df_subido):
    for estandar, sinonimos in MAPEO_ELENA.items():
        for col in df_subido.columns:
            if str(col).lower().strip() in sinonimos:
                df_subido.rename(columns={col: estandar}, inplace=True)
    inventario_global["df"] = df_subido
# ==========================================================
# FIN DEL BLOQUE DE ELENA
# ==========================================================
# --- CONFIGURACIÓN DE SEGURIDAD ADMIN ---
ADMIN_PASSWORD = "18364982" # Cambia esto por uno real
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# --- INICIALIZACIÓN DE DB ---
# Actualiza tu bloque de INICIALIZACIÓN DE BASE DE DATOS
with engine.connect() as conn:
    # Cambia tu código actual por este:
    conn.execute(text("""
       CREATE TABLE IF NOT EXISTS suscripciones (
        id SERIAL PRIMARY KEY,
        email TEXT UNIQUE,
        fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        fecha_vencimiento TEXT,
        plan TEXT DEFAULT 'Individual',
        activo INTEGER DEFAULT 1
       )
    """))

# --- UTILIDADES ---
def limpiar_texto_pdf(texto):
    """Limpia markdown y caracteres no compatibles con PDF estándar"""
    if not texto: return ""
    # Eliminamos rastro de código o formato que la IA pueda enviar por error
    limpio = texto.replace('**', '').replace('###', '').replace('`', '').replace('python', '')
    return limpio.encode('latin-1', 'ignore').decode('latin-1')

class PDFReport(FPDF):
    def header(self):
        if self.page_no() == 1:
            self.set_font('helvetica', 'B', 10)
            self.set_text_color(150, 150, 150)
            self.cell(0, 10, 'AI PRO ANALYST - SISTEMA DE INTELIGENCIA ESTRATÉGICA', 
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
            self.ln(5)

# --- RUTAS ---
@app.route('/')
def index():
    if 'user' not in session:
        return render_template('index.html', login_mode=True)
    
    with engine.connect() as conn:
        query = text("SELECT fecha_vencimiento, creditos_usados, creditos_totales FROM suscripciones WHERE email = :e")
        result = conn.execute(query, {"e": session['user']})
        user_data = result.mappings().fetchone()

    if user_data:
        # Extraer datos con valores por defecto por seguridad
        vencimiento = user_data['fecha_vencimiento']
        usados = user_data['creditos_usados'] if user_data['creditos_usados'] is not None else 0
        totales = user_data['creditos_totales'] if user_data['creditos_totales'] is not None else 5
        
        if isinstance(vencimiento, str):
            vencimiento = datetime.strptime(vencimiento, '%Y-%m-%d').date()
            
        dias_restantes = (vencimiento - date.today()).days

        return render_template('index.html', 
                               login_mode=False, 
                               user=session['user'], 
                               creditos_usados=usados,
                               creditos_totales=totales,
                               dias_restantes=dias_restantes)
    return redirect(url_for('logout'))
@app.route('/login', methods=['POST'])
def login():
    # 1. Limpiamos el correo de espacios y lo pasamos a minúsculas
    email_ingresado = request.form.get('email', '').strip().lower()
    
    with engine.connect() as conn:
        # 2. Buscamos al usuario
        query = text("SELECT email, fecha_vencimiento, activo FROM suscripciones WHERE LOWER(email) = :e")
        result = conn.execute(query, {"e": email_ingresado})
        user = result.mappings().fetchone()
    
    if user:
        # 3. Verificamos si está bloqueado manualmente
        if user['activo'] == 0:
            return render_template('index.html', login_mode=True, error="Cuenta suspendida.")

        # 4. Verificación de fecha con margen de gracia
        from datetime import datetime, timedelta, date
        try:
            hoy = datetime.now().date()
            venc_raw = user['fecha_vencimiento']

            # --- VALIDACIÓN INTELIGENTE DE FECHA ---
            if isinstance(venc_raw, str):
                # Si es texto (viejos datos o SQLite), convertir
                vencimiento_db = datetime.strptime(venc_raw, '%Y-%m-%d').date()
            elif isinstance(venc_raw, (datetime, date)):
                # Si es objeto (Supabase/Postgres), usar directamente
                vencimiento_db = venc_raw if isinstance(venc_raw, date) else venc_raw.date()
            else:
                raise ValueError("Formato de fecha no reconocido")
            # ---------------------------------------

            # Aplicamos el margen de gracia (vencimiento + 1 día)
            if hoy <= (vencimiento_db + timedelta(days=1)):
                session['user'] = user['email']
                return redirect(url_for('index'))
            else:
                return render_template('index.html', login_mode=True, error="Suscripción expirada.")
                
        except Exception as e:
            print(f"Error procesando fecha: {e}")
            return render_template('index.html', login_mode=True, error="Error técnico con la fecha.")

    # 5. Si no se encuentra el correo
    return render_template('index.html', login_mode=True, error="Correo no autorizado.")

@app.route('/upload', methods=['POST'])
def upload():
    if 'user' not in session:
        return jsonify({"error": "Sesión no iniciada"}), 401

    # 1. VALIDACIÓN DE SALDO EN SUPABASE
    user_email = session['user']
    try:
        # Nota: Asegúrate de tener 'supabase' inicializado en tu código
        user_data = supabase.table("usuarios").select("creditos_totales, creditos_usados").eq("email", user_email).single().execute()
        
        if user_data.data:
            if user_data.data['creditos_usados'] >= user_data.data['creditos_totales']:
                return jsonify({
                    "error": "Créditos agotados", 
                    "message": "Has alcanzado el límite de tu plan. Por favor, recarga para continuar."
                }), 403
    except Exception as e:
        print(f"Error consultando créditos: {e}")

    # 2. RECEPCIÓN DEL ARCHIVO
    file = request.files.get('file')
    if not file: 
        return jsonify({"error": "No hay archivo"}), 400
    
    filename = secure_filename(file.filename)
    
    # 3. PROCESAMIENTO E INTEGRACIÓN CON ELENA
    try:
        stream = io.BytesIO(file.read())
        if filename.endswith('.csv'):
            df = pd.read_csv(stream)
        else:
            df = pd.read_excel(stream)

        # --- INICIO INTEGRACIÓN ELENA ---
        # Definimos los nombres de columnas que Elena necesita entender
        MAPEO_ELENA = {
            'Producto': ['producto', 'descripcion', 'nombre', 'articulo', 'item'],
            'Precio Venta': ['precio venta', 'pvp', 'precio', 'venta', 'precio_unitario'],
            'Costo': ['costo', 'compra', 'p.costo'],
            'Stock Actual': ['stock actual', 'stock', 'cantidad', 'existencia']
        }

        # Renombramos las columnas del DF para que coincidan con lo que busca Elena
        for estandar, sinonimos in MAPEO_ELENA.items():
            for col in df.columns:
                if str(col).lower().strip() in sinonimos:
                    df.rename(columns={col: estandar}, inplace=True)
        
        # Guardamos en la memoria global para que Elena pueda responder preguntas de voz/chat
        # Asegúrate de tener definido 'inventario_global = {"df": None, "tasa": 36.50}' al inicio del app.py
        inventario_global["df"] = df.copy() 
        # --- FIN INTEGRACIÓN ELENA ---

        # 4. RESUMEN ESTRUCTURAL PARA AI PRO ANALYST
        resumen = {
            "columnas": df.columns.tolist(),
            "tipos": df.dtypes.astype(str).to_dict(),
            "muestras": df.head(5).to_dict(orient='records'),
            "total_filas": len(df),
            "resumen_numerico": df.describe().to_dict()
        }

        session['resumen_datos'] = resumen
        session['last_file'] = filename
        
        # Si necesitas guardar físicamente para el generador de PDF
        file.seek(0)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        return jsonify({
            "success": True, 
            "filename": filename, 
            "message": "¡Inventario sincronizado con Elena y listo para análisis!"
        })

    except Exception as e:
        return jsonify({"error": f"No se pudo procesar el archivo: {str(e)}"}), 500
@app.route('/chat', methods=['POST'])
def chat():
    user_msg = request.json.get('message', '')
    filename = session.get('last_file')
    resumen = session.get('resumen_datos')
    
    if not filename or not resumen: 
        return jsonify({"response": "Por favor, sube un archivo primero."})
    
    user_email = session.get('user')
    if not user_email:
        return jsonify({"response": "Sesión expirada. Por favor, inicia sesión de nuevo."})

    try:
        # 1. DEFINICIÓN DEL PROMPT BASE
        prompt_sistema = (
            f"Eres un Director de Consultoría Estratégica. Analizando el archivo: {filename}.\n"
            f"Estructura de columnas: {resumen['columnas']}.\n"
            f"Muestra de datos: {resumen['muestras']}.\n\n"
            "INSTRUCCIONES CRÍTICAS:\n"
            "1. Analiza tendencias: identifica recuperaciones o 'rebotes' después de caídas.\n"
            "2. Usa los KPIs reales que se te proporcionan abajo.\n"
            "3. Responde con insights de negocio claros, sin código.\n"
        )

        # 2. INYECCIÓN DE KPIs (Desde el resumen guardado en sesión)
        res_num = resumen.get('resumen_numerico', {})
        if 'Total' in res_num and 'Cantidad' in res_num:
            # Calculamos promedios basados en el resumen de describe()
            try:
                total_est = res_num['Total'].get('mean', 0) * resumen.get('total_filas', 1)
                cant_est = res_num['Cantidad'].get('mean', 1) * resumen.get('total_filas', 1)
                if cant_est > 0:
                    ticket_promedio = total_est / cant_est
                    prompt_sistema += f"\nDATOS REALES: El ticket promedio global es ${ticket_promedio:,.2f}.\n"
            except: pass

        # 3. VALIDACIÓN DE CRÉDITOS USANDO ENGINE (SQLAlchemy)
        with engine.connect() as conn:
            # Consultamos el plan base
            res_plan = conn.execute(text("""
                SELECT creditos_totales, creditos_usados 
                FROM suscripciones 
                WHERE email = :e
            """), {"e": user_email}).mappings().fetchone()
            
            # Consultamos los extras (usando la nueva tabla)
            res_extras = conn.execute(text("""
                SELECT SUM(cantidad) as total_extras 
                FROM creditos_adicionales 
                WHERE email = :e AND estado = 'activo'
            """), {"e": user_email}).mappings().fetchone()

        if res_plan:
            usados = res_plan['creditos_usados'] or 0
            totales_base = res_plan['creditos_totales'] or 0
            total_extras = res_extras['total_extras'] or 0 if res_extras else 0
            
            if usados >= (totales_base + total_extras):
                return jsonify({"response": "⚠️ Has agotado tus créditos. Por favor, recarga tu plan."})

        # 4. DETERMINAR TIPO DE GRÁFICO
        msg_lower = user_msg.lower()
        tipo_grafico = "bar"
        if any(w in msg_lower for w in ["pastel", "pie", "participacion"]): tipo_grafico = "pie"
        elif any(w in msg_lower for w in ["linea", "evolucion", "tendencia"]): tipo_grafico = "line"

        # 5. LLAMADA A LA IA
        response = client.chat.complete(
            model="mistral-small",
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": user_msg}
            ]
        )
        full_response = response.choices[0].message.content

        # 6. ACTUALIZAR CONSUMO Y GUARDAR SESIÓN
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE suscripciones 
                SET creditos_usados = COALESCE(creditos_usados, 0) + 1 
                WHERE email = :e
            """), {"e": user_email})

        session['ultima_pregunta'] = user_msg
        session['ultima_respuesta_ia'] = full_response
        session['tipo_grafico'] = tipo_grafico
        session.modified = True

        return jsonify({
            "response": full_response,
            "nuevo_conteo": usados + 1,
            "total_actualizado": totales_base + total_extras
        })

    except Exception as e:
        print(f"Error en chat: {str(e)}")
        return jsonify({"response": f"Error en el análisis: No se pudo conectar con la base de datos."})
@app.route('/download_pdf')
def download_pdf():
    filename = session.get('last_file')
    pregunta = session.get('ultima_pregunta', 'Análisis General')
    respuesta_ia = session.get('ultima_respuesta_ia', 'Sin datos.')
    tipo = session.get('tipo_grafico', 'bar')
    
    if not filename: return "No hay archivo para generar reporte"
    
    # Cargar datos
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    df = pd.read_csv(filepath) if filename.endswith('.csv') else pd.read_excel(filepath)

    # 1. ESTILO VISUAL BI
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(8, 4.5))
    colors_pro = ['#1a5276', '#1e8449', '#a04000', '#7d3c98', '#2e4053']
    
    # 2. SELECCIÓN DE COLUMNAS
    p_low = pregunta.lower()
    col_num = next((c for c in df.columns if any(x in c.lower() for x in ['total', 'monto', 'venta'])), df.columns[-1])
    
    if any(w in p_low for w in ["vendedor", "quien"]):
        col_cat = next((c for c in df.columns if any(x in c.lower() for x in ['vendedor', 'nombre'])), df.columns[0])
    elif "producto" in p_low:
        col_cat = next((c for c in df.columns if any(x in c.lower() for x in ['producto', 'item'])), df.columns[0])
    else:
        col_cat = next((c for c in df.columns if df[c].dtype == 'object'), df.columns[0])

    # 3. GENERACIÓN DE GRÁFICO
    if tipo == "line" and 'Fecha' in df.columns:
        df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce')
        datos = df.groupby('Fecha')[col_num].sum().sort_index()
        ax.plot(datos.index, datos.values, marker='o', color='#1a5276', linewidth=3)
        ax.fill_between(datos.index, datos.values, color='#1a5276', alpha=0.1)
        tit_g, tit_r = f"Evolución de {col_num}", "REPORTE TEMPORAL"
        
    elif tipo == "pie":
        datos = df.groupby(col_cat)[col_num].sum().sort_values(ascending=False).head(5)
        ax.pie(datos, labels=None, autopct='%1.1f%%', startangle=140, colors=colors_pro, wedgeprops={'edgecolor': 'white', 'linewidth': 2})
        ax.add_artist(plt.Circle((0,0), 0.70, fc='white'))
        ax.legend(datos.index, loc="center left", bbox_to_anchor=(1, 0, 0.5, 1))
        tit_g, tit_r = f"Distribución por {col_cat}", "REPORTE DE PARTICIPACIÓN"
        
    else: # BARRAS
        datos = df.groupby(col_cat)[col_num].sum().sort_values(ascending=False).head(8)
        bars = ax.bar(datos.index, datos.values, color='#2980b9', alpha=0.85)
        for bar in bars:
            height = bar.get_height()
            # Añadimos formato moneda a las etiquetas sobre las barras
            ax.text(bar.get_x()+bar.get_width()/2, height, f'${int(height):,}', ha='center', va='bottom', fontweight='bold')
        tit_g, tit_r = f"Rendimiento por {col_cat}", "REPORTE EJECUTIVO"

    # --- FORMATEO DE MONEDA EN EJE Y ---
    if tipo != "pie":
        fmt = '${x:,.0f}' 
        tick = mtick.StrMethodFormatter(fmt)
        ax.yaxis.set_major_formatter(tick)

    # --- CONFIGURACIÓN ESTÉTICA FINAL (Solo una vez) ---
    ax.set_title(tit_g, fontweight='bold', color='#1a5276', pad=20)
    plt.xticks(rotation=30, ha='right')
    plt.tight_layout()
    
    # Guardar y cerrar
    graph_path = "temp_chart_pro.png"
    plt.savefig(graph_path, dpi=300, bbox_inches='tight')
    plt.close()

    # 4. CONSTRUCCIÓN DEL PDF
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_font("helvetica", 'B', 16)
    pdf.set_text_color(26, 82, 118)
    pdf.cell(0, 10, tit_r, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    
    # Imagen centrada
    pdf.image(graph_path, x=35, y=40, w=140)
    
    # Cuerpo del reporte
    pdf.set_y(140)
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("helvetica", 'B', 12)
    pdf.cell(0, 10, "  CONCLUSIONES DEL ANALISTA", new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
    pdf.ln(3)
    pdf.set_font("helvetica", size=10)
    pdf.set_text_color(0, 0, 0)
    pdf.multi_cell(0, 6, limpiar_texto_pdf(respuesta_ia))

    pdf_output = "reporte_analista_pro.pdf"
    pdf.output(pdf_output)
    
    # Limpieza de archivo temporal
    if os.path.exists(graph_path): os.remove(graph_path)
    
    return send_file(pdf_output, as_attachment=True)
@app.route('/admin', methods=['GET', 'POST'])
def admin_panel():
    auth_key = request.args.get('auth_key')
    if auth_key != ADMIN_PASSWORD:
        return "Acceso denegado. Se requiere auth_key válida.", 403

    if request.method == 'POST':
        email_cliente = request.form.get('email').strip().lower()
        dias = int(request.form.get('dias', 30))
        
        from datetime import datetime, timedelta
        # Calculamos la fecha futura
        vencimiento = (datetime.now() + timedelta(days=dias)).strftime('%Y-%m-%d')
        
        # Usamos engine.begin() para asegurar que Supabase guarde (Commit automático)
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO suscripciones (email, fecha_vencimiento, activo) 
                VALUES (:e, :v, 1)
                ON CONFLICT(email) DO UPDATE SET 
                    fecha_vencimiento = EXCLUDED.fecha_vencimiento,
                    activo = 1
            """), {"e": email_cliente, "v": vencimiento})
        
        return redirect(url_for('admin_panel', auth_key=ADMIN_PASSWORD))

    # Lectura de datos optimizada para el HTML
    with engine.connect() as conn:
        result = conn.execute(text("SELECT id, email, fecha_registro, fecha_vencimiento, activo FROM suscripciones ORDER BY id DESC"))
        # .mappings() permite que en el HTML uses u.email en lugar de u[1]
        usuarios = result.mappings().all() 
    
    return render_template('admin.html', usuarios=usuarios, admin_pass=ADMIN_PASSWORD)
@app.route('/logout')
def logout():
    session.clear() # Limpia toda la sesión por seguridad
    return redirect(url_for('index'))
@app.route('/admin/toggle/<int:user_id>')
def toggle_user(user_id):
    auth_key = request.args.get('auth_key')
    if auth_key != ADMIN_PASSWORD: return "No autorizado", 403
    
    with engine.begin() as conn:
        conn.execute(text("UPDATE suscripciones SET activo = 1 - activo WHERE id = :id"), {"id": user_id})
    return redirect(url_for('admin_panel', auth_key=ADMIN_PASSWORD))
if __name__ == '__main__':
    # Puerto 8000 para Gunicorn / Koyeb
    app.run(host='0.0.0.0', port=8000)