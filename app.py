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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files.get('file')
    if not file: return jsonify({"error": "No hay archivo"}), 400
    try:
        df = pd.read_csv(file) if file.filename.endswith('.csv') else pd.read_excel(file)
        df.columns = [c.strip() for c in df.columns]
        
        conn = sqlite3.connect(DATABASE)
        df.to_sql('ventas', conn, if_exists='replace', index=False)
        conn.close()

        # Generar primer vistazo
        top_v = df.groupby('Vendedor')['Total'].sum().sort_values(ascending=False).head(5)
        return jsonify({
            "reply": "✅ Datos cargados. IA lista para analizar.",
            "chart_data": {"labels": top_v.index.tolist(), "values": top_v.values.tolist(), "title": "Ventas Totales por Vendedor"}
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    pregunta = data.get("message")
    
    try:
        conn = sqlite3.connect(DATABASE)
        df = pd.read_sql_query("SELECT * FROM ventas", conn)
        conn.close()

        # Contexto reducido para ahorrar tokens
        resumen = df.groupby('Vendedor')['Total'].sum().to_dict()
        
        # Lógica de Gráficos
        extra_chart = None
        if "vendedor" in pregunta.lower():
            v_data = df.groupby('Vendedor')['Total'].sum().sort_values(ascending=False).head(5)
            extra_chart = {"labels": v_data.index.tolist(), "values": v_data.values.tolist(), "title": "Ranking de Vendedores"}

        # Consulta a Mistral
        response = client.chat.complete(
            model=model,
            messages=[
                {"role": "system", "content": f"Eres un analista experto. Usa los datos: {resumen}. Responde directo y usa negritas."},
                {"role": "user", "content": pregunta}
            ]
        )
        
        return jsonify({
            "reply": response.choices[0].message.content,
            "new_chart_data": extra_chart
        })
    except Exception as e:
        return jsonify({"error": "Error procesando consulta"}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)