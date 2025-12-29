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

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        user_message = data.get("message")
        
        if not user_message:
            return jsonify({"reply": "Por favor, escribe una pregunta."}), 400

        # --- EXTRACCIÓN DE CONTEXTO REAL ---
        engine = obtener_db_engine()
        with engine.connect() as conn:
            # Consultamos el rendimiento por producto para darle "vista" a la IA
            df_contexto = pd.read_sql("""
                SELECT producto, SUM(total) as ventas_totales, COUNT(*) as transacciones 
                FROM ventas 
                GROUP BY producto 
                ORDER BY ventas_totales DESC
            """, conn)
            
        resumen_datos = df_contexto.to_string(index=False)

        # --- PROMPT REVOLUCIONARIO ---
        prompt_final = f"""
        CONTEXTO DE NEGOCIO REAL:
        {resumen_datos}
        
        PREGUNTA DEL USUARIO:
        {user_message}
        
        INSTRUCCIONES DE PERSONALIDAD (ESTRICTO):
        1. Eres Visionary AI, un Consultor de Negocios de Élite 🚀.
        2. No respondas con texto plano aburrido. Usa negritas, listas y emojis.
        3. Siempre analiza los datos: Si alguien pregunta por bajas ventas, no solo digas el nombre, ¡da una estrategia para mejorar!
        4. Sé proactivo: Si ves que un producto estrella está vendiendo mucho, sugiere felicitar al equipo.
        5. Habla de 'nuestra empresa' o 'tus resultados'.
        """

        chat_response = client.chat.complete(
            model=model_mistral,
            messages=[
                {"role": "system", "content": "Eres el motor de inteligencia de AI Pro Analyst. Tu objetivo es transformar datos en decisiones estratégicas."},
                {"role": "user", "content": prompt_final},
            ]
        )
        
        return jsonify({"reply": chat_response.choices[0].message.content})

    except Exception as e:
        print(f"Error en chat: {str(e)}")
        return jsonify({"reply": "⚠️ Tuve un pequeño problema técnico al consultar los datos. ¿Podrías intentar de nuevo?"}), 500

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)