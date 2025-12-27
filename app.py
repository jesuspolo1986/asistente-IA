import os
import sqlite3
import pandas as pd
from flask import Flask, request, jsonify, render_template
from mistralai import Mistral

app = Flask(__name__)

# Configuración de Mistral
api_key = os.environ.get("MISTRAL_API_KEY")
model = "mistral-large-latest"
client = Mistral(api_key=api_key)

DATABASE = 'database.db'

def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            Fecha TEXT,
            Vendedor TEXT,
            Producto TEXT,
            Cantidad INTEGER,
            Precio_Unitario REAL,
            Total REAL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def obtener_contexto_analitico():
    try:
        conn = sqlite3.connect(DATABASE)
        df = pd.read_sql_query("SELECT * FROM ventas", conn)
        conn.close()
        
        if df.empty:
            return "La base de datos está vacía actualmente."

        # INTELIGENCIA DE DATOS: Pre-procesamos los totales para la IA
        resumen_productos = df.groupby('Producto').agg({
            'Cantidad': 'sum',
            'Total': 'sum',
            'Precio_Unitario': 'first'
        }).sort_values(by='Total', ascending=False).to_dict(orient='index')

        resumen_vendedores = df.groupby('Vendedor').agg({
            'Total': 'sum',
            'Cantidad': 'sum'
        }).to_dict(orient='index')

        total_general = df['Total'].sum()
        conteo_ventas = len(df)

        # Construimos un contexto potente para Mistral
        contexto = (
            f"DATOS CONSOLIDADOS DEL NEGOCIO:\n"
            f"- Total de ventas generales: ${total_general:,.2f}\n"
            f"- Cantidad de transacciones: {conteo_ventas}\n"
            f"- Resumen por Producto (Ventas totales y cantidades): {resumen_productos}\n"
            f"- Resumen por Vendedor (Ingresos generados): {resumen_vendedores}\n"
        )
        return contexto
    except Exception as e:
        return f"Error analizando datos: {e}"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({"error": "No file"}), 400
    
    file = request.files['file']
    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file, sep=None, engine='python')
        else:
            df = pd.read_excel(file)

        # Normalizar nombres de columnas
        df.columns = [c.strip() for c in df.columns]

        conn = sqlite3.connect(DATABASE)
        df.to_sql('ventas', conn, if_exists='replace', index=False)
        conn.close()
        
        return jsonify({"reply": f"✅ ¡Análisis completado! He procesado {len(df)} registros. Ya puedes consultar métricas avanzadas."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_message = data.get("message")
    
    # Obtenemos el resumen inteligente
    contexto_pro = obtener_contexto_analitico()

    try:
        chat_response = client.chat.complete(
            model=model,
            messages=[
                {
                    "role": "system", 
                    "content": (
                        "Eres AI Pro Analyst, un experto consultor de negocios. "
                        "Tienes acceso a estos datos consolidados que ya han sido calculados: \n"
                        f"{contexto_pro}\n"
                        "Usa estos datos para responder de forma estratégica, profesional y con tablas Markdown."
                    )
                },
                {"role": "user", "content": user_message}
            ]
        )
        return jsonify({"reply": chat_response.choices[0].message.content})
    except Exception as e:
        return jsonify({"error": "Error en la consulta"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)