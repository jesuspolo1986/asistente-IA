from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import os
import pandas as pd
import io
import base64
import matplotlib
matplotlib.use('Agg') # Optimizado para servidores
import matplotlib.pyplot as plt
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from mistralai import Mistral

app = Flask(__name__)
app.secret_key = "analista_pro_v3_predictivo"
app.config['UPLOAD_FOLDER'] = 'uploads'

# --- CONFIGURACIÓN DE ENTORNO ---
DATABASE_URL = os.environ.get("DATABASE_URL", "").replace("postgres://", "postgresql://", 1)
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")

engine = create_engine(DATABASE_URL, pool_size=5, max_overflow=10, pool_pre_ping=True)
client = Mistral(api_key=MISTRAL_API_KEY)

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

@app.route('/')
def index():
    if 'user' not in session: return render_template('index.html', login_mode=True)
    
    email = session['user']
    hoy = datetime.now().date()
    
    with engine.connect() as conn:
        res = conn.execute(text("SELECT fecha_vencimiento, creditos_usados FROM suscripciones WHERE email = :e"), {"e": email}).fetchone()
    
    if not res: return redirect(url_for('logout'))
    
    vence, usados = res[0], res[1] or 0
    banner = None
    
    # Lógica de Gracia Personalizada
    if hoy <= vence: 
        estado = "Activo"
    elif hoy == vence + timedelta(days=1): 
        estado = "Gracia"
        banner = ("⚠️ Recordatorio: Tu suscripción expiró ayer. Tienes un día de gracia.", "alert-warning")
    else: 
        estado = "Vencido"
        banner = ("🚫 Suscripción expirada. Por favor, renueva para continuar.", "alert-danger")
        
    return render_template('index.html', login_mode=False, user=email, estado=estado, creditos=usados, banner=banner)

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email').strip().lower()
    session['user'] = email
    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO suscripciones (email, fecha_vencimiento) 
            VALUES (:e, CURRENT_DATE + INTERVAL '30 days') 
            ON CONFLICT (email) DO NOTHING
        """), {"e": email})
        conn.commit()
    return redirect(url_for('index'))

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files: return jsonify({"error": "No hay archivo"}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({"error": "Sin nombre"}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    session['last_file'] = filename
    return jsonify({"success": True, "message": f"Análisis de '{filename}' listo."})

# ... (mismas importaciones anteriores)

@app.route('/chat', methods=['POST'])
def chat():
    user_msg = request.json.get('message', '').lower()
    filename = session.get('last_file')
    email = session.get('user')
    
    if not filename:
        return jsonify({"response": "Sube un archivo primero."})

    try:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        df = pd.read_csv(filepath) if filename.endswith('.csv') else pd.read_excel(filepath)
        
        # --- MOTOR DE INTELIGENCIA SENIOR (PRE-PROCESAMIENTO) ---
        # 1. Calculamos la eficiencia real (Revenue per Unit) por vendedor
        eficiencia = df.groupby('Vendedor').apply(
            lambda x: x['Total'].sum() / x['Cantidad'].sum()
        ).to_dict()

        # 2. Identificamos productos con mayor margen de ingresos
        pareto_productos = df.groupby('Producto')['Total'].sum().sort_values(ascending=False).head(3).to_dict()

        # 3. Detectamos anomalías de precio (Precios diferentes para el mismo producto)
        anomalias_precio = df.groupby('Producto')['Precio_Unitario'].nunique()
        alertas_precio = anomalias_precio[anomalias_precio > 1].index.tolist()

        # --- PROMPT DE NIVEL SENIOR ESTRATÉGICO ---
        prompt_sistema = f"""
        ERES: Un Director de Analítica de Datos (CDO). Tu objetivo es la RENTABILIDAD.
        
        CONTEXTO PRE-PROCESADO PARA TI:
        - Eficiencia de Vendedores (Ingreso/Unidad): {eficiencia}
        - Top 3 Productos (Pareto): {pareto_productos}
        - Alertas de inconsistencia de precio en: {alertas_precio}
        
        INSTRUCCIONES DE RESPUESTA:
        1. NO menciones promedios simples. Habla de EFICIENCIA y COSTO DE OPORTUNIDAD.
        2. Si un vendedor tiene eficiencia baja, sugiérele un cambio de estrategia (ej. vender productos de mayor valor).
        3. PREDICCIÓN: Basado en los datos, ¿qué pasará si no se cambia nada?
        4. Tono: Directo, ejecutivo y crítico. No felicites, da órdenes de negocio.
        5. Prohibido mostrar código Python o hablar de librerías.
        """
        
        # --- GENERACIÓN DE GRÁFICO AVANZADO ---
        chart_b64 = None
        if any(word in user_msg for word in ["gráfico", "visualiza", "barras", "análisis"]):
            plt.figure(figsize=(10, 6))
            # Graficamos eficiencia en lugar de solo totales (Análisis más Senior)
            pd.Series(eficiencia).sort_values().plot(kind='barh', color='#10b981')
            plt.title("Eficiencia de Ventas (USD Generados por Unidad)")
            plt.xlabel("Dólares por cada producto movido")
            plt.tight_layout()
            
            buf = io.BytesIO()
            plt.savefig(buf, format='png')
            buf.seek(0)
            chart_b64 = base64.b64encode(buf.getvalue()).decode()
            plt.close()

        # --- LLAMADA A MISTRAL (MODELO SMALL O MEDIUM) ---
        response = client.chat.complete(
            model="mistral-small", # El cerebro Senior necesita razonamiento complejo
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": user_msg}
            ]
        )
        
        # Actualización de créditos
        with engine.connect() as conn:
            conn.execute(text("UPDATE suscripciones SET creditos_usados = creditos_usados + 1 WHERE email = :e"), {"e": email})
            conn.commit()

        return jsonify({
            "response": response.choices[0].message.content,
            "chart": chart_b64
        })

    except Exception as e:
        return jsonify({"response": f"Error de análisis: {str(e)}"})
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))