import os
import re
import pandas as pd
import matplotlib
matplotlib.use('Agg') # Necesario para correr en servidores sin interfaz gráfica
import matplotlib.pyplot as plt
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, send_file
from sqlalchemy import create_engine, text
from werkzeug.utils import secure_filename
from mistralai import Mistral
from fpdf import FPDF
from fpdf.enums import XPos, YPos

app = Flask(__name__)
app.secret_key = "analista_pro_2026_final_v1"
app.config['UPLOAD_FOLDER'] = 'uploads'

# --- CONFIGURACIÓN DE SERVICIOS ---
DATABASE_URL = "sqlite:///local_analista.db"
MISTRAL_API_KEY = "p2KCokd08zRypMAZQxMbC4ImxkM5DPK1" # Reemplaza con tu clave de Mistral

engine = create_engine(DATABASE_URL)
client = Mistral(api_key=MISTRAL_API_KEY)

# Crear carpeta de subidas si no existe
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# --- INICIALIZACIÓN DE BASE DE DATOS ---
with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS suscripciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            fecha_vencimiento TEXT
        )
    """))
    conn.commit()

# --- CLASES Y UTILIDADES ---
def limpiar_texto_pdf(texto):
    """Limpia caracteres especiales para evitar errores en FPDF"""
    if not texto: return ""
    return texto.encode('latin-1', 'ignore').decode('latin-1')

class PDFReport(FPDF):
    def header(self):
        if self.page_no() == 1:
            self.set_font('helvetica', 'B', 10)
            self.set_text_color(150, 150, 150)
            self.cell(0, 10, 'AI PRO ANALYST - SISTEMA DE INTELIGENCIA ESTRATÉGICA', 
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
            self.ln(5)

# --- RUTAS DE NAVEGACIÓN ---
@app.route('/')
def index():
    if 'user' not in session:
        return render_template('index.html', login_mode=True)
    return render_template('index.html', login_mode=False, user=session['user'])

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email').strip().lower()
    session['user'] = email
    # Registro automático del usuario con suscripción hasta fin de año
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

# --- MOTOR DE CHAT ---
@app.route('/chat', methods=['POST'])
def chat():
    user_msg = request.json.get('message', '')
    filename = session.get('last_file')
    if not filename: return jsonify({"response": "Por favor, sube un archivo primero para comenzar el análisis."})
    
    try:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        df = pd.read_csv(filepath) if filename.endswith('.csv') else pd.read_excel(filepath)
        
        # Lógica de detección de columnas para el contexto de la IA
        msg_lower = user_msg.lower()
        resumen_temporal = ""
        
        # Darle a la IA datos específicos si pregunta por fechas
        if any(w in msg_lower for w in ["día", "fecha", "evolución", "cuándo"]):
            if 'Fecha' in df.columns:
                df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce').dt.strftime('%Y-%m-%d')
                v_max = df.groupby('Fecha')['Total'].sum().idxmax()
                resumen_temporal = f"Dato clave: El día con más ventas fue {v_max}."

        # Determinar intención de gráfico
        tipo_grafico = "bar"
        if any(w in msg_lower for w in ["pastel", "pie", "dona", "participación"]): tipo_grafico = "pie"
        elif any(w in msg_lower for w in ["linea", "evolucion", "tendencia"]): tipo_grafico = "line"

        prompt_sistema = (
            f"Eres un Analista de Datos Senior. Archivo: {filename}.\n"
            f"Columnas: {list(df.columns)}.\n"
            f"Muestra: {df.head(5).to_dict()}.\n{resumen_temporal}\n"
            "Responde de forma ejecutiva y precisa."
        )

        response = client.chat.complete(
            model="mistral-small",
            messages=[{"role": "system", "content": prompt_sistema}, {"role": "user", "content": user_msg}]
        )
        
        # Guardar en sesión para el PDF
        session['ultima_pregunta'] = user_msg
        session['ultima_respuesta_ia'] = response.choices[0].message.content
        session['tipo_grafico'] = tipo_grafico
        
        return jsonify({"response": response.choices[0].message.content})
    except Exception as e:
        return jsonify({"response": f"Error procesando el análisis: {str(e)}"})

# --- GENERADOR DE PDF PROFESIONAL ---
@app.route('/download_pdf')
def download_pdf():
    filename = session.get('last_file')
    pregunta = session.get('ultima_pregunta', 'Análisis General')
    respuesta_ia = session.get('ultima_respuesta_ia', 'Sin datos.')
    tipo = session.get('tipo_grafico', 'bar')
    
    if not filename: return "Error: No hay datos"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    df = pd.read_csv(filepath) if filename.endswith('.csv') else pd.read_excel(filepath)

    # 1. ESTILO DE GRÁFICO (Business Intelligence)
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(8, 4.5))
    colors_pro = ['#1a5276', '#1e8449', '#a04000', '#7d3c98', '#2e4053']
    
    # 2. PUNTERÍA LÁSER (Selección de columnas)
    p_low = pregunta.lower()
    if any(w in p_low for w in ["vendedor", "quien"]):
        col_cat = next((c for c in df.columns if 'vendedor' in c.lower() or 'nombre' in c.lower()), df.columns[0])
    elif "producto" in p_low:
        col_cat = next((c for c in df.columns if 'producto' in c.lower() or 'item' in c.lower()), df.columns[0])
    else:
        col_cat = next((c for c in df.columns if df[c].dtype == 'object'), df.columns[0])

    col_num = next((c for c in df.columns if any(x in c.lower() for x in ['total', 'monto', 'cantidad'])), df.columns[-1])

    # 3. CONSTRUCCIÓN VISUAL
    if tipo == "line" or "fecha" in p_low:
        df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce')
        datos = df.groupby('Fecha')[col_num].sum().sort_index()
        ax.plot(datos.index, datos.values, marker='o', color='#1a5276', linewidth=3)
        ax.fill_between(datos.index, datos.values, color='#1a5276', alpha=0.1)
        titulo_grafico, titulo_rep = f"Tendencia de {col_num}", "REPORTE DE EVOLUCIÓN"
    elif tipo == "pie":
        datos = df.groupby(col_cat)[col_num].sum().sort_values(ascending=False).head(5)
        ax.pie(datos, labels=None, autopct='%1.1f%%', startangle=140, colors=colors_pro, wedgeprops={'edgecolor': 'white', 'linewidth': 2})
        ax.add_artist(plt.Circle((0,0), 0.70, fc='white')) # Efecto Dona
        ax.legend(datos.index, loc="center left", bbox_to_anchor=(1, 0, 0.5, 1))
        titulo_grafico, titulo_rep = f"Participación por {col_cat}", "REPORTE DE DISTRIBUCIÓN"
    else:
        datos = df.groupby(col_cat)[col_num].sum().sort_values(ascending=False).head(8)
        bars = ax.bar(datos.index, datos.values, color='#2980b9', alpha=0.85)
        for bar in bars:
            ax.text(bar.get_x()+bar.get_width()/2, bar.get_height(), int(bar.get_height()), ha='center', va='bottom', fontweight='bold')
        titulo_grafico, titulo_rep = f"Ranking: {col_num} por {col_cat}", "REPORTE DE RENDIMIENTO"

    ax.set_title(titulo_grafico, fontweight='bold', color='#1a5276', pad=20)
    plt.xticks(rotation=30, ha='right')
    plt.tight_layout()
    
    graph_path = "temp_chart.png"
    plt.savefig(graph_path, dpi=300, bbox_inches='tight')
    plt.close()

    # 4. GENERACIÓN DE PDF
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_font("helvetica", 'B', 16)
    pdf.set_text_color(26, 82, 118)
    pdf.cell(0, 10, titulo_rep, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    pdf.image(graph_path, x=35, y=40, w=140)
    
    pdf.set_y(140)
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("helvetica", 'B', 12)
    pdf.cell(0, 10, "  ANÁLISIS ESTRATÉGICO", new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
    pdf.set_font("helvetica", size=10)
    pdf.multi_cell(0, 6, limpiar_texto_pdf(respuesta_ia))

    pdf_output = "reporte_analista.pdf"
    pdf.output(pdf_output)
    if os.path.exists(graph_path): os.remove(graph_path)
    return send_file(pdf_output, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True, port=8000)