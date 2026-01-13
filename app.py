import os
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Necesario para entornos de servidor (Koyeb/Heroku)
import matplotlib.pyplot as plt
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, send_file
from sqlalchemy import create_engine, text
from werkzeug.utils import secure_filename
from mistralai import Mistral
from fpdf import FPDF
from fpdf.enums import XPos, YPos

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
    
    email = session['user']
    with engine.connect() as conn:
        user = conn.execute(text("SELECT fecha_vencimiento FROM suscripciones WHERE email = :e"), {"e": email}).fetchone()
    
    if user:
        from datetime import datetime
        # Convertimos la fecha de la DB a objeto datetime
        vencimiento = datetime.strptime(user[0], '%Y-%m-%d').date()
        hoy = datetime.now().date()
        
        # Calculamos la diferencia de días
        delta = (vencimiento - hoy).days
        
        # LÓGICA DE GRACIA: 
        # Si delta es 0: Vence hoy.
        # Si delta es -1: Es el día de gracia (venció ayer).
        # Si delta < -1: Ya no tiene acceso.
        
        if delta >= -1:
            return render_template('index.html', 
                                 login_mode=False, 
                                 user=email, 
                                 dias_restantes=delta)
    
    # Si no hay usuario o ya pasó el día de gracia
    session.pop('user', None)
    return render_template('index.html', login_mode=True, error="Tu suscripción y periodo de gracia han expirado.")
@app.route('/login', methods=['POST'])
def login():
    # 1. Limpiamos el correo de espacios y lo pasamos a minúsculas
    email_ingresado = request.form.get('email', '').strip().lower()
    
    with engine.connect() as conn:
        # 2. Buscamos al usuario (usamos mappings para evitar errores de índice)
        query = text("SELECT email, fecha_vencimiento, activo FROM suscripciones WHERE LOWER(email) = :e")
        result = conn.execute(query, {"e": email_ingresado})
        user = result.mappings().fetchone()
    
    if user:
        # 3. Verificamos si está bloqueado manualmente
        if user['activo'] == 0:
            return render_template('index.html', login_mode=True, error="Cuenta suspendida.")

        # 4. Verificación de fecha con margen de gracia
        from datetime import datetime, timedelta
        try:
            # Convertimos la fecha de la DB (texto) a objeto date
            hoy = datetime.now().date()
            vencimiento_db = datetime.strptime(user['fecha_vencimiento'], '%Y-%m-%d').date()

# Con el día de gracia (vencimiento + 1), el usuario debería entrar sin problema
            if hoy <= (vencimiento_db + timedelta(days=1)):
                session['user'] = user['email']
                return redirect(url_for('index'))
            else:
                return render_template('index.html', login_mode=True, error="Suscripción expirada.")
        except Exception as e:
            print(f"Error procesando fecha: {e}")
            return render_template('index.html', login_mode=True, error="Error en formato de fecha.")

    # 5. Si no se encuentra el correo
    return render_template('index.html', login_mode=True, error="Correo no autorizado.")
@app.route('/upload', methods=['POST'])
def upload():
    file = request.files.get('file')
    if not file: return jsonify({"error": "No hay archivo"}), 400
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    session['last_file'] = filename
    return jsonify({"success": True, "filename": filename})

@app.route('/chat', methods=['POST'])
def chat():
    user_msg = request.json.get('message', '')
    filename = session.get('last_file')
    if not filename: return jsonify({"response": "Por favor, sube un archivo primero."})
    
    try:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        df = pd.read_csv(filepath) if filename.endswith('.csv') else pd.read_excel(filepath)
        
        # Lógica de detección de gráfico y fechas
        msg_lower = user_msg.lower()
        resumen_temporal = ""
        if 'Fecha' in df.columns and any(w in msg_lower for w in ["día", "fecha", "evolución"]):
            df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce').dt.strftime('%Y-%m-%d')
            v_max = df.groupby('Fecha')['Total'].sum().idxmax()
            resumen_temporal = f"Contexto histórico: El pico de ingresos fue el {v_max}."

        tipo_grafico = "bar"
        if any(w in msg_lower for w in ["pastel", "pie", "dona", "participación"]): tipo_grafico = "pie"
        elif any(w in msg_lower for w in ["linea", "evolucion", "tendencia"]): tipo_grafico = "line"

        # SENIOR: Prompt blindado para evitar código en el PDF
        prompt_sistema = (
            f"Eres un Director de Consultoría Estratégica. Analizando: {filename}.\n"
            f"Estructura de datos: {list(df.columns)}.\n"
            f"Muestra: {df.head(3).to_dict()}.\n{resumen_temporal}\n"
            "REGLA DE ORO: Responde solo con INSIGHTS DE NEGOCIO. "
            "PROHIBIDO incluir código Python, bloques de Pandas o explicaciones técnicas. "
            "Usa un tono ejecutivo, enfocado en rentabilidad y porcentajes."
        )

        response = client.chat.complete(
            model="mistral-small",
            messages=[{"role": "system", "content": prompt_sistema}, {"role": "user", "content": user_msg}]
        )
        
        full_response = response.choices[0].message.content
        session['ultima_pregunta'] = user_msg
        session['ultima_respuesta_ia'] = full_response
        session['tipo_grafico'] = tipo_grafico
        
        return jsonify({"response": full_response})
    except Exception as e:
        return jsonify({"response": f"Error en el análisis: {str(e)}"})

@app.route('/download_pdf')
def download_pdf():
    filename = session.get('last_file')
    pregunta = session.get('ultima_pregunta', 'Análisis General')
    respuesta_ia = session.get('ultima_respuesta_ia', 'Sin datos.')
    tipo = session.get('tipo_grafico', 'bar')
    
    if not filename: return "No hay archivo para generar reporte"
    
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    df = pd.read_csv(filepath) if filename.endswith('.csv') else pd.read_excel(filepath)

    # 1. ESTILO VISUAL BI
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(8, 4.5))
    colors_pro = ['#1a5276', '#1e8449', '#a04000', '#7d3c98', '#2e4053']
    
    # 2. PUNTERÍA LÁSER (Selección de columnas)
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
    else:
        datos = df.groupby(col_cat)[col_num].sum().sort_values(ascending=False).head(8)
        bars = ax.bar(datos.index, datos.values, color='#2980b9', alpha=0.85)
        for bar in bars:
            ax.text(bar.get_x()+bar.get_width()/2, bar.get_height(), f'{int(bar.get_height())}', ha='center', va='bottom', fontweight='bold')
        tit_g, tit_r = f"Rendimiento por {col_cat}", "REPORTE EJECUTIVO"

    ax.set_title(tit_g, fontweight='bold', color='#1a5276', pad=20)
    plt.xticks(rotation=30, ha='right')
    plt.tight_layout()
    
    graph_path = "temp_chart_pro.png"
    plt.savefig(graph_path, dpi=300, bbox_inches='tight')
    plt.close()

    # 4. CONSTRUCCIÓN DEL PDF
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_font("helvetica", 'B', 16)
    pdf.set_text_color(26, 82, 118)
    pdf.cell(0, 10, tit_r, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    pdf.image(graph_path, x=35, y=40, w=140)
    
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