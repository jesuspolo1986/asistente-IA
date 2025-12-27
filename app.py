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
        return f"Error al procesar contexto: {e}"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files.get('file')
    if not file: return jsonify({"error": "No file"}), 400
    try:
        # Leer archivo (CSV o Excel)
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file, sep=None, engine='python')
        else:
            df = pd.read_excel(file)
            
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
            "chart_data": chart_data
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    pregunta = data.get("message").lower()
    contexto = obtener_contexto_analitico()
    
    try:
        conn = sqlite3.connect(DATABASE)
        df = pd.read_sql_query("SELECT * FROM ventas", conn)
        conn.close()

        extra_data = None
        # Gráficos dinámicos basados en la pregunta
        if "vendedor" in pregunta or "vendedores" in pregunta:
            v_data = df.groupby('Vendedor')['Total'].sum().sort_values(ascending=False)
            extra_data = {"labels": v_data.index.tolist(), "values": v_data.values.tolist(), "title": "Ventas por Vendedor"}
        
        elif "producto" in pregunta or "ranking" in pregunta or "pareto" in pregunta:
            p_data = df.groupby('Producto')['Total'].sum().sort_values(ascending=False).head(5)
            extra_data = {"labels": p_data.index.tolist(), "values": p_data.values.tolist(), "title": "Top 5 Productos"}

        # LLAMADA A MISTRAL (Corregida)
        chat_response = client.chat.complete(
            model=model,
            messages=[
                {"role": "system", "content": f"Eres AI Pro Analyst. Usa tablas y negritas. Datos: {contexto}"},
                {"role": "user", "content": pregunta}
            ],
            max_tokens=800,
            temperature=0.1
        )
        
        return jsonify({
            "reply": chat_response.choices[0].message.content,
            "new_chart_data": extra_data
        })
    except Exception as e:
        print(f"Error en chat: {e}") # Log para Koyeb
        return jsonify({"error": "Error procesando la consulta de IA"}), 500

if __name__ == '__main__':
    # Usar el puerto de la variable de entorno para despliegue
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)