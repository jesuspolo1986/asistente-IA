import os
import pandas as pd
from sqlalchemy import create_engine, text

# --- CONFIGURACIÓN ---
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

def create_tables():
    """Limpia la base de datos y crea la tabla 'ventas' con 6 columnas."""
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS planilla_notas CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS ventas CASCADE;"))
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
    print("Base de datos lista: Tabla 'ventas' creada.")

def cargar_archivo_a_bd(file_path):
    """Procesa CSV/Excel y los sube a la tabla 'ventas'."""
    try:
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path, sep=None, engine='python', encoding='utf-8-sig')
        else:
            df = pd.read_excel(file_path)

        # Normalizar nombres de columnas
        df.columns = [str(c).strip().lower().replace(' ', '_') for c in df.columns]

        with engine.begin() as conn:
            df.to_sql('ventas', con=conn, if_exists='append', index=False, method='multi')
        
        return True, f"¡Éxito! {len(df)} registros cargados."
    except Exception as e:
        return False, f"Error al procesar: {str(e)}"