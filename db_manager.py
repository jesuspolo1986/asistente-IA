import os
import pandas as pd
from sqlalchemy import create_engine, text

# --- CONFIGURACIÓN DE CONEXIÓN ---
DATABASE_URL = os.environ.get("DATABASE_URL")

# Corrección de protocolo para SQLAlchemy 1.4+ (Vital para Koyeb/Heroku)
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Crear motor SQLAlchemy
# pool_pre_ping ayuda a reconectar si la base de datos se "duerme"
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# --- CREACIÓN Y LIMPIEZA DE TABLAS ---
def create_tables():
    """Limpia versiones antiguas y crea la tabla con la estructura de Ventas Pro."""
    with engine.begin() as conn:
        # Borramos tablas antiguas para evitar conflictos de columnas
        conn.execute(text("DROP TABLE IF EXISTS planilla_notas CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS ventas CASCADE;"))
        
        # Estructura final para tu ventas_demo.csv
        conn.execute(text("""
            CREATE TABLE ventas (
                id SERIAL PRIMARY KEY,
                fecha DATE,
                vendedor VARCHAR(100),
                producto VARCHAR(100),
                cantidad INT,
                precio_unitario FLOAT,
                total FLOAT
            );
        """))
    print("Base de datos reseteada: Tabla 'ventas' lista con 6 columnas.")

# --- EJECUCIÓN DE CONSULTAS DINÁMICAS (Para Gemini) ---
def execute_dynamic_query(query: str):
    try:
        with engine.connect() as conn:
            result = conn.execute(text(query))
            # Manejo de comandos que no devuelven filas (INSERT, DELETE, etc.)
            if not result.returns_rows:
                return [], [], "Operación exitosa."
            
            columns = result.keys()
            rows = result.fetchall()
            return columns, rows, None
    except Exception as e:
        return [], [], str(e)

# --- CARGA DE EXCEL/CSV A LA BD ---
def cargar_archivo_a_bd(file_path: str):
    """Carga archivos CSV o Excel usando Pandas con normalización de columnas."""
    try:
        # sep=None detecta automáticamente si usas , o ; en el CSV
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path, sep=None, engine='python', encoding='utf-8-sig')
        else:
            df = pd.read_excel(file_path)

        # Normalizar nombres: "Precio Unitario" -> "precio_unitario"
        df.columns = [str(c).strip().lower().replace(' ', '_') for c in df.columns]

        # Carga masiva rápida
        with engine.begin() as conn:
            df.to_sql('ventas', con=conn, if_exists='append', index=False, method='multi')

        return True, f"Éxito: Se sincronizaron {len(df)} registros correctamente."
    except Exception as e:
        return False, f"Error al procesar archivo: {str(e)}"