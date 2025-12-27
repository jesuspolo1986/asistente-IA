import os
from sqlalchemy import create_engine, text
import pandas as pd

# --- CONFIGURACIÓN DE CONEXIÓN ---
DATABASE_URL = os.environ.get("DATABASE_URL")

# Cambiamos el esquema para usar pg8000
# Ejemplo: postgresql://user:pass@host:port/dbname
DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+pg8000://")

# Crear motor SQLAlchemy con pg8000
engine = create_engine(DATABASE_URL, echo=True, future=True)

# --- CREACIÓN DE TABLAS ---
def create_tables():
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ventas (
                id SERIAL PRIMARY KEY,
                producto VARCHAR(100),
                cantidad INT,
                precio FLOAT
            )
        """))

# --- EJECUCIÓN DE CONSULTAS DINÁMICAS ---
def execute_dynamic_query(query: str):
    try:
        with engine.connect() as conn:
            result = conn.execute(text(query))
            columns = result.keys()
            rows = result.fetchall()
        return columns, rows, None
    except Exception as e:
        return [], [], str(e)

# --- CARGA DE EXCEL A LA BD ---
def cargar_excel_a_bd(file_path: str):
    try:
        df = pd.read_excel(file_path)

        # Insertar filas en la tabla ventas
        with engine.begin() as conn:
            for _, row in df.iterrows():
                conn.execute(text("""
                    INSERT INTO ventas (producto, cantidad, precio)
                    VALUES (:producto, :cantidad, :precio)
                """), {
                    "producto": str(row["producto"]),
                    "cantidad": int(row["cantidad"]),
                    "precio": float(row["precio"])
                })

        return True, "Datos cargados exitosamente en la tabla ventas."
    except Exception as e:
        return False, f"Error al cargar Excel: {str(e)}"
from sqlalchemy import create_engine, text
import os

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

def preparar_base_de_datos():
    with engine.connect() as conn:
        # Borramos la tabla vieja si existe para empezar de cero con Ventas
        conn.execute(text("DROP TABLE IF EXISTS planilla_notas CASCADE;"))
        
        # Creamos la nueva tabla de Ventas
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ventas (
                id SERIAL PRIMARY KEY,
                fecha DATE,
                vendedor VARCHAR(100),
                producto VARCHAR(100),
                cantidad INT,
                precio_unitario FLOAT,
                total FLOAT
            );
        """))
        conn.commit()
    print("Base de datos lista para recibir ventas.")
