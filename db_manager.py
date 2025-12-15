# db_manager.py (VERSION ACTUALIZADA CON ESQUEMA EXPANDIDO)
# db_manager.py (VERSIÓN FINAL SEGURA PARA RENDER)

import sqlite3
import os
from faker import Faker
import random
from datetime import datetime, timedelta

DB_NAME = 'supermercado.db'
fake = Faker('es_ES')

# --- Datos Fijos de Ejemplo (para consistencia) ---
CATEGORIAS_LISTA = ["Lácteos", "Panadería", "Frutas y Verduras", "Carnes", "Abarrotes", "Bebidas", "Limpieza"]
CIUDADES_FIJAS = [
    (1, 'Bogotá', 'Colombia'),
    (2, 'Medellín', 'Colombia'),
    (3, 'Cali', 'Colombia'),
    (4, 'Barranquilla', 'Colombia'),
    (5, 'Ciudad de México', 'México'),
    (6, 'Monterrey', 'México')
]
PRODUCTOS_BASE = [
    ("Leche Entera", 3.50, 1), ("Yogurt Natural", 2.00, 1), 
    ("Pan Integral", 2.50, 2), ("Croissant", 1.50, 2), 
    ("Manzanas", 0.75, 3), ("Tomates", 0.50, 3), 
    ("Carne de Res", 15.00, 4), ("Pechuga de Pollo", 8.00, 4),
    ("Arroz 1kg", 1.20, 5), ("Frijoles 500g", 1.80, 5),
    ("Gaseosa Cola", 1.75, 6), ("Agua Mineral", 1.00, 6)
]


def create_connection():
    """Crea una conexión a la base de datos SQLite."""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    except sqlite3.Error as e:
        print(f"Error al conectar con SQLite: {e}")
        return None

def create_tables(conn):
    """Crea todas las tablas del esquema si no existen."""
    cursor = conn.cursor()

    sql_create_ciudades_table = """
    CREATE TABLE IF NOT EXISTS Ciudades (
        id_ciudad INTEGER PRIMARY KEY,
        nombre_ciudad TEXT NOT NULL,
        pais TEXT NOT NULL
    );
    """
    sql_create_categorias_table = """
    CREATE TABLE IF NOT EXISTS Categorias (
        id_categoria INTEGER PRIMARY KEY,
        nombre_categoria TEXT NOT NULL UNIQUE
    );
    """
    sql_create_sucursales_table = """
    CREATE TABLE IF NOT EXISTS Sucursales (
        id_sucursal INTEGER PRIMARY KEY,
        nombre_sucursal TEXT NOT NULL,
        id_ciudad INTEGER,
        direccion TEXT,
        FOREIGN KEY (id_ciudad) REFERENCES Ciudades (id_ciudad)
    );
    """
    sql_create_clientes_table = """
    CREATE TABLE IF NOT EXISTS Clientes (
        id_cliente INTEGER PRIMARY KEY,
        nombre TEXT NOT NULL,
        apellido TEXT NOT NULL,
        edad INTEGER,
        id_ciudad INTEGER,
        email TEXT UNIQUE,
        FOREIGN KEY (id_ciudad) REFERENCES Ciudades (id_ciudad)
    );
    """
    sql_create_productos_table = """
    CREATE TABLE IF NOT EXISTS Productos (
        id_producto INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL UNIQUE,
        precio REAL NOT NULL,
        stock INTEGER NOT NULL,
        fecha_vencimiento TEXT, 
        id_categoria INTEGER,
        FOREIGN KEY (id_categoria) REFERENCES Categorias (id_categoria)
    );
    """
    sql_create_ventas_table = """
    CREATE TABLE IF NOT EXISTS Ventas (
        id_venta INTEGER PRIMARY KEY AUTOINCREMENT,
        id_cliente INTEGER,
        id_sucursal INTEGER,
        fecha_venta TEXT NOT NULL, 
        total REAL NOT NULL,
        FOREIGN KEY (id_cliente) REFERENCES Clientes (id_cliente),
        FOREIGN KEY (id_sucursal) REFERENCES Sucursales (id_sucursal)
    );
    """
    sql_create_detalle_venta_table = """
    CREATE TABLE IF NOT EXISTS DetalleVenta (
        id_detalle INTEGER PRIMARY KEY AUTOINCREMENT,
        id_venta INTEGER,
        id_producto INTEGER,
        cantidad INTEGER NOT NULL,
        subtotal REAL NOT NULL,
        FOREIGN KEY (id_venta) REFERENCES Ventas (id_venta),
        FOREIGN KEY (id_producto) REFERENCES Productos (id_producto)
    );
    """
    
    try:
        cursor.execute(sql_create_ciudades_table)
        cursor.execute(sql_create_categorias_table) 
        cursor.execute(sql_create_sucursales_table) 
        cursor.execute(sql_create_clientes_table)
        cursor.execute(sql_create_productos_table)
        cursor.execute(sql_create_ventas_table)
        cursor.execute(sql_create_detalle_venta_table)
        conn.commit()
    except sqlite3.Error as e:
        print(f"Error al crear tablas: {e}")

# --- Funciones de Generación Masiva (Solo para uso local) ---

def generate_base_data(conn):
    """Inserta Ciudades, Categorías, Sucursales y Productos fijos."""
    cursor = conn.cursor()

    # Ciudades
    cursor.executemany("INSERT INTO Ciudades (id_ciudad, nombre_ciudad, pais) VALUES (?, ?, ?)", CIUDADES_FIJAS)
    
    # Categorías
    categorias_data = [(i + 1, nombre) for i, nombre in enumerate(CATEGORIAS_LISTA)]
    cursor.executemany("INSERT INTO Categorias (id_categoria, nombre_categoria) VALUES (?, ?)", categorias_data)

    # Sucursales (2 por ciudad principal)
    sucursales_data = []
    id_sucursal = 1
    for id_ciudad, nombre_ciudad, _ in CIUDADES_FIJAS[:4]: 
        sucursales_data.append((id_sucursal, f"Central {nombre_ciudad}", id_ciudad, fake.street_address()))
        id_sucursal += 1
        sucursales_data.append((id_sucursal, f"Norte {nombre_ciudad}", id_ciudad, fake.street_address()))
        id_sucursal += 1
    cursor.executemany("INSERT INTO Sucursales (id_sucursal, nombre_sucursal, id_ciudad, direccion) VALUES (?, ?, ?, ?)", sucursales_data)

    # Productos (con asignación de categoría)
    productos_data = [(nombre, precio, stock, (datetime.now() + timedelta(days=random.randint(15, 365))).strftime('%Y-%m-%d'), id_cat) 
                      for nombre, precio, id_cat in PRODUCTOS_BASE for stock in [random.randint(50, 200)]]
    
    sql_productos = "INSERT INTO Productos (nombre, precio, stock, fecha_vencimiento, id_categoria) VALUES (?, ?, ?, ?, ?)"
    cursor.executemany(sql_productos, productos_data)

    conn.commit()
    return [item[0] for item in CIUDADES_FIJAS], [id_cat for id_cat, _ in categorias_data], [id_sucursal - 1 for id_sucursal, _, _, _ in sucursales_data]

def generate_clientes(conn, num_clientes=500):
    """Genera una gran cantidad de clientes aleatorios."""
    cursor = conn.cursor()
    clientes_data = []
    ciudades_ids = [c[0] for c in CIUDADES_FIJAS]
    
    for i in range(1, num_clientes + 1):
        edad = random.randint(18, 75)
        id_ciudad = random.choice(ciudades_ids)
        nombre = fake.first_name()
        apellido = fake.last_name()
        email = f"{nombre.lower()}.{apellido.lower()}{random.randint(1,99)}@{fake.domain_name()}"
        clientes_data.append((i, nombre, apellido, edad, id_ciudad, email))

    sql_clientes = "INSERT INTO Clientes (id_cliente, nombre, apellido, edad, id_ciudad, email) VALUES (?, ?, ?, ?, ?, ?)"
    cursor.executemany(sql_clientes, clientes_data)
    conn.commit()
    return num_clientes

def generate_ventas_y_detalles(conn, num_ventas=5000, num_clientes=500):
    """Genera una gran cantidad de ventas y detalles de venta asociados."""
    cursor = conn.cursor()
    
    productos_ids = [row[0] for row in cursor.execute("SELECT id_producto FROM Productos").fetchall()]
    sucursales_ids = [row[0] for row in cursor.execute("SELECT id_sucursal FROM Sucursales").fetchall()]
    
    if not productos_ids or not sucursales_ids:
        print("Error: No hay productos o sucursales disponibles.")
        return

    ventas_data = []
    detalle_data = []
    
    # Rango de fechas: Últimos 6 meses
    end_date = datetime.now()
    start_date = end_date - timedelta(days=180)

    for id_venta in range(1, num_ventas + 1):
        
        id_cliente = random.randint(1, num_clientes)
        id_sucursal = random.choice(sucursales_ids)
        fecha_venta = fake.date_time_between(start_date=start_date, end_date=end_date).strftime('%Y-%m-%d %H:%M:%S')
        total_venta = 0.0

        num_items = random.randint(1, 5)
        productos_venta = random.sample(productos_ids, k=num_items)

        for id_producto in productos_venta:
            cantidad = random.randint(1, 5)
            
            precio = cursor.execute("SELECT precio FROM Productos WHERE id_producto = ?", (id_producto,)).fetchone()[0]
            subtotal = precio * cantidad
            total_venta += subtotal
            
            detalle_data.append((id_venta, id_producto, cantidad, round(subtotal, 2)))
        
        ventas_data.append((id_venta, id_cliente, id_sucursal, fecha_venta, round(total_venta, 2)))

    cursor.executemany("INSERT INTO Ventas (id_venta, id_cliente, id_sucursal, fecha_venta, total) VALUES (?, ?, ?, ?, ?)", ventas_data)
    sql_detalle = "INSERT INTO DetalleVenta (id_venta, id_producto, cantidad, subtotal) VALUES (?, ?, ?, ?)"
    cursor.executemany(sql_detalle, detalle_data)
    conn.commit()
    print(f"Generadas {num_ventas} ventas y {len(detalle_data)} ítems de detalle.")


def seed_data(conn):
    """Coordina la generación de todos los datos."""
    print("Iniciando la generación de datos de demostración realistas...")
    
    # 1. Borrar datos antiguos (si existen)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM DetalleVenta")
    cursor.execute("DELETE FROM Ventas")
    cursor.execute("DELETE FROM Productos")
    cursor.execute("DELETE FROM Clientes")
    cursor.execute("DELETE FROM Sucursales")
    cursor.execute("DELETE FROM Categorias")
    cursor.execute("DELETE FROM Ciudades")
    conn.commit()
    
    # 2. Generar datos base
    generate_base_data(conn)
    print("Datos base (Ciudades, Categorías, Sucursales, Productos) generados.")

    # 3. Generar Clientes (500)
    num_clientes = 500
    generate_clientes(conn, num_clientes)
    print(f"Generados {num_clientes} clientes aleatorios.")

    # 4. Generar Ventas (5000)
    num_ventas = 5000
    generate_ventas_y_detalles(conn, num_ventas, num_clientes)
    print("Generación de datos finalizada.")


# --- Función principal de Configuración ---

def main_db_setup():
    """Configura la conexión y crea las tablas. NO LLENA DATOS."""
    conn = create_connection()
    if conn:
        create_tables(conn)
        # IMPORTANTE: seed_data(conn) HA SIDO ELIMINADO DE AQUÍ
        return conn

def execute_dynamic_query(conn, sql_query):
    """Ejecuta una consulta SQL dinámica generada por la IA."""
    cleaned_query = sql_query.strip().upper()
    
    # CÓDIGO DE SEGURIDAD (SELECT ONLY)
    if not cleaned_query.startswith("SELECT"):
        return None, None, "ERROR DE SEGURIDAD: Solo se permiten consultas de tipo SELECT."
        
    if cleaned_query.replace(";", "", 1).count(';') > 0:
        return None, None, "ERROR DE SEGURIDAD: Se detectaron múltiples comandos en la consulta."
    
    try:
        cur = conn.cursor()
        cur.execute(sql_query)
        
        if cur.description:
            columns = [description[0] for description in cur.description]
            rows = cur.fetchall()
            return columns, rows, None
        else:
            return None, None, "Consulta ejecutada sin resultados (no es SELECT)."
    
    except sqlite3.OperationalError as e:
        return None, None, str(e)
    except Exception as e:
        return None, None, f"Error desconocido al ejecutar SQL: {e}"


# --- Bloque para EJECUTAR LOCALMENTE el llenado de datos ---
if __name__ == '__main__':
    # Este bloque solo se ejecuta al correr 'python db_manager.py' en local
    conn = create_connection()
    if conn:
        create_tables(conn)
        seed_data(conn) # <--- SOLO AQUI SE LLENA LA BASE DE DATOS
        conn.close()