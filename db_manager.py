import os
import pandas as pd
from sqlalchemy import create_engine, text

# --- CONFIGURACIÓN DE CONEXIÓN ---
DATABASE_URL = os.environ.get("DATABASE_URL")

# Corrección de protocolo para SQLAlchemy 1.4+
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Crear motor SQLAlchemy (eliminamos pg8000 si no lo tienes en requirements, 
# psycopg2 es el estándar que Koyeb maneja mejor por defecto)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# --- CREACIÓN Y LIMPIEZA DE TABLAS ---
def preparar_base_de_datos():
    """Limpia versiones antiguas y crea la tabla con la estructura de Ventas Pro."""
    with engine.begin() as conn:
        # Borramos tablas antiguas para evitar conflictos de columnas
        conn.execute(text("DROP TABLE IF EXISTS planilla_notas CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS ventas CASCADE;"))
        
        # Creamos la tabla nueva con las 6 columnas que tiene tu ventas_demo.csv
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
            # Si la consulta no devuelve filas (como un INSERT o DROP)
            if not result.returns_rows:
                return [], [], "Operación exitosa (sin filas devueltas)."
            
            columns = result.keys()
            rows = result.fetchall()
            return columns, rows, None
    except Exception as e:
        return [], [], str(e)

# --- CARGA DE EXCEL/CSV A LA BD ---
def cargar_archivo_a_bd(file_path: str):
    """Carga archivos CSV o Excel usando Pandas para mayor velocidad."""
    try:
        # Lectura inteligente
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path, sep=None, engine='python', encoding='utf-8-sig')
        else:
            df = pd.read_excel(file_path)

        # Normalizar nombres de columnas para que coincidan con la DB
        # Esto convierte "Precio Unitario" en "precio_unitario"
        df.columns = [str(c).strip().lower().replace(' ', '_') for c in df.columns]

        # Carga masiva eficiente
        with engine.begin() as conn:
            df.to_sql('ventas', con=conn, if_exists='append', index=False, method='multi')

        return True, f"Éxito: Se sincronizaron {len(df)} registros correctamente."
    except Exception as e:
        return False, f"Error al procesar archivo: {str(e)}"