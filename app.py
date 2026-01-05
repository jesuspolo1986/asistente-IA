from flask import Flask
from sqlalchemy import create_engine, text
import os

app = Flask(__name__)

# Configuración de la base de datos desde la variable de entorno de Koyeb
DATABASE_URL = os.environ.get("DATABASE_URL", "").replace("postgres://", "postgresql://", 1)
engine = create_engine(DATABASE_URL)

@app.route('/')
def test_connection():
    try:
        # Intentamos una consulta que no requiere tablas, solo le pedimos la hora al servidor
        with engine.connect() as conn:
            result = conn.execute(text("SELECT now();")).fetchone()
            return f"<h1>✅ ¡CONECTADO A SUPABASE!</h1><p>Hora de la DB: {result[0]}</p>", 200
    except Exception as e:
        return f"<h1>❌ ERROR DE CONEXIÓN</h1><p>Detalle: {str(e)}</p>", 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))