import os
import psycopg2
from psycopg2.extras import RealDictCursor
from faker import Faker
import random
from datetime import datetime, timedelta

# Configuración de Faker
fake = Faker('es_ES')

# --- Datos Fijos ---
CATEGORIAS_LISTA = ["Lácteos", "Panadería", "Frutas y Verduras", "Carnes", "Abarrotes", "Bebidas", "Limpieza"]
CIUDADES_FIJAS = [
    (1, 'Bogotá', 'Colombia'), (2, 'Medellín', 'Colombia'),
    (3, 'Cali', 'Colombia'), (4, 'Barranquilla', 'Colombia'),
    (5, 'Ciudad de México', 'México'), (6, 'Monterrey', 'México')
]
PRODUCTOS_BASE = [
    ("Leche Entera", 3.50, 1), ("Yogurt Natural", 2.00, 1), 
    ("Pan Integral", 2.50, 2), ("Croissant", 1.50, 2), 
    ("Manzanas", 0.75, 3), ("Tomates", 0.50, 3), 
    ("Carne de Res", 15.00, 4), ("Pechuga de Pollo", 8.00, 4),
    ("Arroz 1kg", 1.20, 5), ("Frijoles 500g", 1.80, 5),
    ("Gaseosa Cola", 1.75, 6), ("Agua Mineral", 1.00, 6)
]

def get_db_connection():
    """Establece conexión con PostgreSQL en Render."""
    db_url = os.environ.get("DATABASE_URL")
    try:
        # sslmode='require' es vital para servicios en la nube como Render
        conn = psycopg2.connect(db_url, sslmode='require')
        return conn
    except Exception as e:
        print(f"❌ Error de conexión Cloud: {e}")
        return None

def create_tables():
    """Crea las tablas en PostgreSQL (usando sintaxis compatible)."""
    conn = get_db_connection()
    if not conn: return
    
    cur = conn.cursor()
    # En PostgreSQL usamos SERIAL para autoincremento en lugar de AUTOINCREMENT
    commands = [
        "CREATE TABLE IF NOT EXISTS Ciudades (id_ciudad INT PRIMARY KEY, nombre_ciudad TEXT NOT NULL, pais TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS Categorias (id_categoria INT PRIMARY KEY, nombre_categoria TEXT NOT NULL UNIQUE)",
        "CREATE TABLE IF NOT EXISTS Sucursales (id_sucursal INT PRIMARY KEY, nombre_sucursal TEXT NOT NULL, id_ciudad INT REFERENCES Ciudades(id_ciudad), direccion TEXT)",
        "CREATE TABLE IF NOT EXISTS Clientes (id_cliente INT PRIMARY KEY, nombre TEXT NOT NULL, apellido TEXT NOT NULL, edad INT, id_ciudad INT REFERENCES Ciudades(id_ciudad), email TEXT UNIQUE)",
        "CREATE TABLE IF NOT EXISTS Productos (id_producto SERIAL PRIMARY KEY, nombre TEXT NOT NULL UNIQUE, precio DECIMAL(10,2) NOT NULL, stock INT NOT NULL, fecha_vencimiento DATE, id_categoria INT REFERENCES Categorias(id_categoria))",
        "CREATE TABLE IF NOT EXISTS Ventas (id_venta SERIAL PRIMARY KEY, id_cliente INT REFERENCES Clientes(id_cliente), id_sucursal INT REFERENCES Sucursales(id_sucursal), fecha_venta TIMESTAMP NOT NULL, total DECIMAL(12,2) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS DetalleVenta (id_detalle SERIAL PRIMARY KEY, id_venta INT REFERENCES Ventas(id_venta), id_producto INT REFERENCES Productos(id_producto), cantidad INT NOT NULL, subtotal DECIMAL(10,2) NOT NULL)"
    ]
    
    try:
        for cmd in commands:
            cur.execute(cmd)
        conn.commit()
        print("✅ Tablas creadas/verificadas en PostgreSQL")
    except Exception as e:
        print(f"❌ Error creando tablas: {e}")
    finally:
        cur.close()
        conn.close()

# --- Sembrado de datos (Optimizado para Postgres) ---

def seed_data():
    conn = get_db_connection()
    if not conn: return
    cur = conn.cursor()
    
    print("🧹 Limpiando tablas antiguas...")
    tablas = ["DetalleVenta", "Ventas", "Productos", "Clientes", "Sucursales", "Categorias", "Ciudades"]
    for t in tablas: cur.execute(f"TRUNCATE {t} RESTART IDENTITY CASCADE;")

    # 1. Ciudades y Categorías
    cur.executemany("INSERT INTO Ciudades VALUES (%s, %s, %s)", CIUDADES_FIJAS)
    cur.executemany("INSERT INTO Categorias VALUES (%s, %s)", [(i+1, n) for i, n in enumerate(CATEGORIAS_LISTA)])

    # 2. Productos
    for nombre, precio, id_cat in PRODUCTOS_BASE:
        venc = (datetime.now() + timedelta(days=random.randint(30,300))).date()
        cur.execute("INSERT INTO Productos (nombre, precio, stock, fecha_vencimiento, id_categoria) VALUES (%s, %s, %s, %s, %s)",
                    (nombre, precio, random.randint(50,200), venc, id_cat))

    # 3. Clientes (Demo 100)
    for i in range(1, 101):
        cur.execute("INSERT INTO Clientes VALUES (%s, %s, %s, %s, %s, %s)",
                    (i, fake.first_name(), fake.last_name(), random.randint(18,70), random.randint(1,6), fake.email()))

    conn.commit()
    print("🚀 Base de Datos Cloud poblada con éxito")
    cur.close()
    conn.close()

def execute_dynamic_query(sql_query):
    """Ejecuta consultas generadas por Gemini en la nube."""
    conn = get_db_connection()
    if not conn: return None, None, "Error de conexión cloud."
    
    try:
        # Usamos RealDictCursor para que el resultado sea fácil de leer para la IA
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql_query)
        
        if cur.description:
            rows = cur.fetchall()
            # Convertimos RealDict a lista de dicts estándar
            return list(rows[0].keys()) if rows else [], [list(r.values()) for r in rows], None
        return None, None, "Consulta sin resultados."
    except Exception as e:
        return None, None, str(e)
    finally:
        conn.close()

if __name__ == '__main__':
    # Ejecución manual para inicializar la nube
    create_tables()
    seed_data()