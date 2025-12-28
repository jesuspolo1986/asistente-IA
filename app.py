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

        total_gral = df['Total'].sum()
        # Resumen para que la IA no se pierda en 100 filas
        prod_stats = df.groupby('Producto')['Total'].sum().sort_values(ascending=False).head(5).to_dict()
        vend_stats = df.groupby('Vendedor')['Total'].sum().sort_values(ascending=False).head(5).to_dict()
        
        contexto = (
            f"DATOS DE NEGOCIO:\n"
            f"- Total Ventas: ${total_gral:,.2f}\n"
            f"- Top Productos: {prod_stats}\n"
            f"- Top Vendedores: {vend_stats}\n"
        )
        return contexto
    except Exception as e:
        return f"Error de contexto: {e}"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files.get('file')
    if not file: return jsonify({"error": "No file"}), 400
    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file, sep=None, engine='python')
        else:
            df = pd.read_excel(file)
            
        df.columns = [c.strip() for c in df.columns]
        
        conn = sqlite3.connect(DATABASE)
        df.to_sql('ventas', conn, if_exists='replace', index=False)
        conn.close()

        # Gráfico inicial
        top_p = df.groupby('Producto')['Total'].sum().sort_values(ascending=False).head(5)
        return jsonify({
            "reply": "✅ Datos cargados. IA lista para analizar.",
            "chart_data": {"labels": top_p.index.tolist(), "values": top_p.values.tolist(), "title": "Top 5 Productos"}
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    pregunta = data.get("message")
    contexto = obtener_contexto_analitico()
    
    try:
        conn = sqlite3.connect(DATABASE)
        df = pd.read_sql_query("SELECT * FROM ventas", conn)
        conn.close()

        extra_data = None
        p_lower = pregunta.lower()
        
        if "vendedor" in p_lower:
            v_data = df.groupby('Vendedor')['Total'].sum().sort_values(ascending=False).head(5)
            extra_data = {"labels": v_data.index.tolist(), "values": v_data.values.tolist(), "title": "Ranking de Vendedores"}
        
        elif "producto" in p_lower or "ventas" in p_lower:
            p_data = df.groupby('Producto')['Total'].sum().sort_values(ascending=False).head(5)
            extra_data = {"labels": p_data.index.tolist(), "values": p_data.values.tolist(), "title": "Ventas por Producto"}

        chat_response = client.chat.complete(
            model=model,
            messages=[
                {"role": "system", "content": f"Eres AI Pro Analyst. Responde con negritas y brevedad. Contexto: {contexto}"},
                {"role": "user", "content": pregunta}
            ]
        )
        
        return jsonify({
            "reply": chat_response.choices[0].message.content,
            "new_chart_data": extra_data
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)