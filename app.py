import os
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Necesario para entornos de servidor (Koyeb/Heroku)
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, send_file
from sqlalchemy import create_engine, text
from werkzeug.utils import secure_filename
from mistralai import Mistral
from fpdf import FPDF
import io
from werkzeug.utils import secure_filename
from fpdf.enums import XPos, YPos
from datetime import datetime, date
app = Flask(__name__)
# SENIOR: Priorizar variables de entorno para seguridad
app.secret_key = os.environ.get("FLASK_SECRET", "analista_pro_2026_top_secret")
app.config['UPLOAD_FOLDER'] = 'uploads'

# --- CONFIGURACIÓN DE SERVICIOS ---
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    DATABASE_URL = "postgresql://postgres:aSxRZ3rVrMu2Oasu@db.kebpamfydhnxeaeegulx.supabase.co:6543/postgres"

# 3. Corrección técnica para SQLAlchemy + Postgres
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "p2KCokd08zRypMAZQxMbC4ImxkM5DPK1")

engine = create_engine(DATABASE_URL)
client = Mistral(api_key=MISTRAL_API_KEY)

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

    # 1. VALIDACIÓN DE CRÉDITOS (Supabase)
    user_email = session['user']
    try:
        user_data = supabase.table("usuarios").select("creditos_totales, creditos_usados").eq("email", user_email).single().execute()
        if user_data.data and user_data.data['creditos_usados'] >= user_data.data['creditos_totales']:
            return jsonify({"error": "Créditos agotados", "message": "Por favor, recarga tu plan."}), 403
    except Exception as e:
        print(f"Error consultando créditos: {e}")

    # 2. PROCESAMIENTO DEL ARCHIVO
    file = request.files.get('file')
    if not file: return jsonify({"error": "No hay archivo"}), 400
    
    filename = secure_filename(file.filename)
    
    try:
        stream = io.BytesIO(file.read())
        df = pd.read_csv(stream) if filename.endswith('.csv') else pd.read_excel(stream)

        # --- NIVEL SUPERIOR: CÁLCULOS ESTADÍSTICOS REALES ---
        # Calculamos todo en Python para que la IA no tenga que adivinar
        kpis_reales = {
            "total_facturacion": float(df['Total'].sum()),
            "total_unidades": int(df['Cantidad'].sum()),
            "ticket_promedio": float(df['Total'].mean()),
            "top_vendedores": df.groupby('Vendedor')['Total'].sum().nlargest(5).to_dict(),
            "top_productos": df.groupby('Producto')['Total'].sum().nlargest(5).to_dict(),
            "conteo_transacciones": len(df),
            "vendedor_mas_activo": df['Vendedor'].value_counts().idxmax()
        }

        resumen = {
            "columnas": df.columns.tolist(),
            "kpis": kpis_reales,
            "muestras": df.head(10).to_dict(orient='records') # Solo para contexto visual
        }

        session['resumen_datos'] = resumen
        session['last_file'] = filename
        session.modified = True

        return jsonify({
            "success": True, 
            "message": "Inventario analizado con precisión. Los KPIs han sido calculados con éxito."
        })

    except Exception as e:
        return jsonify({"error": f"Error al procesar: {str(e)}"}), 500
@app.route('/chat', methods=['POST'])
def chat():
    user_msg = request.json.get('message', '')
    filename = session.get('last_file')
    resumen = session.get('resumen_datos')
    
    if not filename or not resumen: 
        return jsonify({"response": "Por favor, sube un archivo primero."})
    
    user_email = session.get('user')
    kpis = resumen.get('kpis', {})

    try:
        # 1. PROMPT ESTRATÉGICO CON DATOS VERÍDICOS
        prompt_sistema = (
            f"Eres un Director de Estrategia auditando el archivo: {filename}.\n"
            f"AUDITORÍA REAL DEL SISTEMA (USA ESTOS DATOS):\n"
            f"- Facturación Total: ${kpis['total_facturacion']:,.2f}\n"
            f"- Ticket Promedio: ${kpis['ticket_promedio']:,.2f}\n"
            f"- Líderes en Ventas: {kpis['top_vendedores']}\n"
            f"- Productos más vendidos: {kpis['top_productos']}\n"
            f"- Total de Transacciones: {kpis['conteo_transacciones']}\n\n"
            
            "REGLAS:\n"
            "1. No inventes datos. Si te preguntan por un vendedor, usa los 'Líderes en Ventas' arriba.\n"
            "2. Estructura tu respuesta en: Hallazgo, Análisis de Tendencia y Recomendación ROI.\n"
            "3. Mantén un tono ejecutivo y profesional."
        )

        # 2. LLAMADA A MISTRAL AI
        response = client.chat.complete(
            model="mistral-small",
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": user_msg}
            ]
        )
        full_response = response.choices[0].message.content

        # 3. ACTUALIZACIÓN DE CRÉDITOS (Atomicidad con Engine)
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE usuarios 
                SET creditos_usados = COALESCE(creditos_usados, 0) + 1 
                WHERE email = :e
            """), {"e": user_email})

        return jsonify({
            "response": full_response,
            "status": "success"
        })

    except Exception as e:
        print(f"Error en chat: {e}")
        return jsonify({"response": "Lo siento, el motor de análisis tuvo un error técnico."})pp.route('/download_pdf')
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