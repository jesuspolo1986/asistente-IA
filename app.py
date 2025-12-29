from flask import Flask, request, jsonify, render_template
import os
import pandas as pd
from sqlalchemy import create_engine
from werkzeug.utils import secure_filename
# IMPORTANTE: Añade estas dos líneas para Mistral
from mistralai import Mistral 

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'

# --- CONFIGURACIÓN DE MISTRAL ---
# Usa una variable de entorno para mayor seguridad en Koyeb
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "TU_API_KEY_AQUI")
client = Mistral(api_key=MISTRAL_API_KEY)
model_mistral = "mistral-large-latest" 

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def procesar_y_cargar_excel(file_path):
    DATABASE_URL = os.environ.get("DATABASE_URL")
    if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    
    if not DATABASE_URL:
        return False, "Error de configuración de BD", None

    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    
    try:
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path, sep=None, engine='python', encoding='utf-8-sig')
        else:
            df = pd.read_excel(file_path)
        
        df.columns = [str(c).strip().lower().replace(' ', '_') for c in df.columns]

        # Lógica de KPIs
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

        with engine.begin() as connection:
            df.to_sql('ventas', con=connection, if_exists='append', index=False, method='multi')
        
        return True, f"Éxito: {len(df)} registros cargados.", summary
    except Exception as e:
        return False, str(e), None

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"success": False, "message": "No hay archivo"}), 400
    
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
            return jsonify({"reply": "No se recibió ningún mensaje."}), 400

        # Llamada corregida a Mistral
        chat_response = client.chat.complete(
            model=model_mistral,
            messages=[
                {"role": "user", "content": user_message},
            ]
        )
        
        ai_reply = chat_response.choices[0].message.content
        return jsonify({"reply": ai_reply})

    except Exception as e:
        print(f"Error en Mistral: {str(e)}")
        return jsonify({"reply": "Error conectando con Mistral AI."}), 500

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)