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
            Fecha TEXT, Vendedor TEXT, Producto TEXT, 
            Cantidad INTEGER, Precio_Unitario REAL, Total REAL
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
        
        if df.empty: return "Sin datos."

        # Analítica de precisión para la IA
        total_gral = df['Total'].sum()
        prod_stats = df.groupby('Producto').agg({'Total': 'sum', 'Cantidad': 'sum'}).sort_values(by='Total', ascending=False).to_dict(orient='index')
        matriz_exacta = df.groupby(['Vendedor', 'Producto'])['Total'].sum().unstack(fill_value=0).to_dict(orient='index')
        
        contexto = (
            f"SISTEMA DE INTELIGENCIA DE NEGOCIOS\n"
            f"TOTAL FACTURADO: ${total_gral:,.2f}\n"
            f"PERFORMANCE POR PRODUCTO: {prod_stats}\n"
            f"MATRIZ DE VENTAS POR VENDEDOR: {matriz_exacta}\n"
        )
        return contexto
    except Exception as e:
        return f"Error: {e}"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files.get('file')
    if not file: return jsonify({"error": "No file"}), 400
    try:
        # Leer archivo
        df = pd.read_csv(file, sep=None, engine='python') if file.filename.endswith('.csv') else pd.read_excel(file)
        df.columns = [c.strip() for c in df.columns]
        
        # Guardar en SQLite
        conn = sqlite3.connect(DATABASE)
        df.to_sql('ventas', conn, if_exists='replace', index=False)
        conn.close()

        # PREPARAR DATOS PARA EL GRÁFICO (Top 5 productos)
        top_productos = df.groupby('Producto')['Total'].sum().sort_values(ascending=False).head(5)
        chart_data = {
            "labels": top_productos.index.tolist(),
            "values": top_productos.values.tolist()
        }
        
        return jsonify({
            "reply": "🚀 Base de datos actualizada. Análisis y visualización listos.",
            "chart_data": chart_data  # Esto activa la gráfica en el frontend
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    contexto = obtener_contexto_analitico()
    try:
        chat_response = client.chat.complete(
            model=model,
            messages=[
                {"role": "system", "content": f"Eres AI Pro Analyst. Responde con datos EXACTOS basados en: {contexto}. Usa tablas y negritas."},
                {"role": "user", "content": data.get("message")}
            ]
        )
        return jsonify({"reply": chat_response.choices[0].message.content})
    except Exception as e:
        return jsonify({"error": "Error de conexión"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)