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
DATABASE_URL = "sqlite:///local_analista.db"
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "p2KCokd08zRypMAZQxMbC4ImxkM5DPK1")

engine = create_engine(DATABASE_URL)
client = Mistral(api_key=MISTRAL_API_KEY)

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# --- INICIALIZACIÓN DE DB ---
with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS suscripciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            fecha_vencimiento TEXT
        )
    """))
    conn.commit()

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
    return render_template('index.html', login_mode='user' not in session, user=session.get('user'))

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email', '').strip().lower()
    session['user'] = email
    with engine.connect() as conn:
        conn.execute(text("INSERT OR IGNORE INTO suscripciones (email, fecha_vencimiento) VALUES (:e, '2026-12-31')"), {"e": email})
        conn.commit()
    return redirect(url_for('index'))

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

if __name__ == '__main__':
    # Usar puerto 8000 para consistencia con Gunicorn
    app.run(host='0.0.0.0', port=8000)