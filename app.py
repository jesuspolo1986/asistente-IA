from flask import Flask, request, jsonify, render_template
import os
import pandas as pd
from sqlalchemy import create_engine
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'

# Aseguramos que la carpeta de subidas exista
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- FUNCIÓN DE PROCESAMIENTO (La que revisamos) ---
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

# --- RUTA DE CARGA (UPLOAD) ---
# CORRECTO
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"success": False, "message": "No hay archivo"}), 400
    
    file = request.files['file']
    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(file_path)

    # Llamamos a la función y capturamos el summary
    success, message, summary = procesar_y_cargar_excel(file_path)

    # ESTA ES LA CLAVE: Enviamos el summary de vuelta al Dashboard
    return jsonify({
        "success": success, 
        "message": message, 
        "summary": summary
    })

# --- RUTA DE CHAT (SIMULADA) ---
@app.route('/chat', methods=['POST'])
def chat():
    # Aquí iría tu lógica actual de conexión con la IA
    pass

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)