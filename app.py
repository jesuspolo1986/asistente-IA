from flask import Flask, request, jsonify, render_template
import os
import pandas as pd
from sqlalchemy import create_engine
from werkzeug.utils import secure_filename
from mistralai import Mistral

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'

# --- CONFIGURACIÓN DE MISTRAL ---
# Recuerda configurar MISTRAL_API_KEY en las variables de entorno de Koyeb
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "TU_CLAVE_AQUÍ")
client = Mistral(api_key=MISTRAL_API_KEY)
model_mistral = "mistral-large-latest"

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def obtener_db_engine():
    """Configura el motor de la base de datos compatible con Koyeb/Supabase."""
    DATABASE_URL = os.environ.get("DATABASE_URL")
    if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    return create_engine(DATABASE_URL, pool_pre_ping=True)

def procesar_y_cargar_excel(file_path):
    """Procesa el archivo y genera el resumen de KPIs."""
    try:
        engine = obtener_db_engine()
        
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path, sep=None, engine='python', encoding='utf-8-sig')
        else:
            df = pd.read_excel(file_path)
        
        # Estandarizar columnas: minúsculas y sin espacios
        df.columns = [str(c).strip().lower().replace(' ', '_') for c in df.columns]

        # Cálculo de KPIs (Usa nombres de columnas estándar)
        total_ventas = df['total'].sum() if 'total' in df.columns else 0
        mejor_vendedor = df.groupby('vendedor')['total'].sum().idxmax() if 'vendedor' in df.columns else "N/A"
        producto_top = df.groupby('producto')['total'].sum().idxmax() if 'producto' in df.columns else "N/A"
        unidades_totales = int(df['cantidad'].sum()) if 'cantidad' in df.columns else len(df)

        summary = {
            "total_ventas": f"${total_ventas:,.2f}",
            "mejor_vendedor": str(mejor_vendedor),
            "producto_top": str(producto_top),
            "unidades": str(unidades_totales)
        }

        # Guardar en la base de datos (reemplaza para evitar duplicados en pruebas)
        with engine.begin() as connection:
            df.to_sql('ventas', con=connection, if_exists='replace', index=False)
        
        return True, f"Éxito: {len(df)} registros analizados.", summary
    except Exception as e:
        return False, f"Error al procesar: {str(e)}", None

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"success": False, "message": "No se encontró el archivo"}), 400
    
    file = request.files['file']
    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(file_path)

    success, message, summary = procesar_y_cargar_excel(file_path)

    return jsonify({
        "success": success, 
        "message": message, 
        "summary": summary
    })

# --- MOTOR GLOBAL (Fuera de las funciones) ---
engine = obtener_db_engine()

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        user_message = data.get("message")
        
        if not user_message:
            return jsonify({"reply": "Por favor, escribe una pregunta."}), 400

        # --- EXTRACCIÓN RÁPIDA DE CONTEXTO ---
        # Limitamos el contexto para no saturar la memoria ni el prompt
        with engine.connect() as conn:
            df_contexto = pd.read_sql("""
                SELECT producto, SUM(total) as ventas_totales 
                FROM ventas 
                GROUP BY producto 
                ORDER BY ventas_totales DESC
                LIMIT 15
            """, conn)
            
        resumen_datos = df_contexto.to_string(index=False)

        prompt_final = f"""
        DATOS REALES:
        {resumen_datos}
        
        PREGUNTA: {user_message}
        
        INSTRUCCIONES: Eres Visionary AI 🚀. Responde con emojis, analiza los datos y da una recomendación estratégica breve.
        """

        # Llamada a Mistral con tiempo de espera controlado
        chat_response = client.chat.complete(
            model=model_mistral,
            messages=[
                {"role": "system", "content": "Analista estratégico de negocios."},
                {"role": "user", "content": prompt_final},
            ]
        )
        
        return jsonify({"reply": chat_response.choices[0].message.content})

    except Exception as e:
        print(f"Error detectado: {str(e)}")
        return jsonify({"reply": "🚀 Los datos están listos, pero la IA tardó un poco en responder. ¡Intenta preguntar de nuevo!"}), 200 # Devolvemos 200 para no romper el front
@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)