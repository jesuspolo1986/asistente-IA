# db_manager.py (VERSION ACTUALIZADA CON ESQUEMA EXPANDIDO)

import sqlite3
import os

DB_NAME = 'supermercado.db'

def create_connection():
    """Crea una conexión a la base de datos SQLite."""
    conn = None
    try:
        # Crea el archivo de base de datos si no existe
        conn = sqlite3.connect(DB_NAME)
        # Habilita la integridad referencial (claves foráneas)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    except sqlite3.Error as e:
        print(f"Error al conectar con SQLite: {e}")
        return None

def create_tables(conn):
    """Crea todas las tablas del esquema si no existen."""
    cursor = conn.cursor()

    # --- Definiciones de Tablas (Nuevas y Modificadas) ---

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
    
    # PRODUCTOS AHORA TIENE id_categoria
    sql_create_productos_table = """
    CREATE TABLE IF NOT EXISTS Productos (
        id_producto INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL UNIQUE,
        precio REAL NOT NULL,
        stock INTEGER NOT NULL,
        fecha_vencimiento TEXT, -- Formato YYYY-MM-DD
        id_categoria INTEGER,
        FOREIGN KEY (id_categoria) REFERENCES Categorias (id_categoria)
    );
    """

    # VENTAS AHORA TIENE id_sucursal
    sql_create_ventas_table = """
    CREATE TABLE IF NOT EXISTS Ventas (
        id_venta INTEGER PRIMARY KEY AUTOINCREMENT,
        id_cliente INTEGER,
        id_sucursal INTEGER,
        fecha_venta TEXT NOT NULL, -- Formato YYYY-MM-DD HH:MM:SS
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
        # Ejecución en el orden de dependencias
        cursor.execute(sql_create_ciudades_table)
        cursor.execute(sql_create_categorias_table)  # NUEVO
        cursor.execute(sql_create_sucursales_table)  # NUEVO
        cursor.execute(sql_create_clientes_table)
        cursor.execute(sql_create_productos_table)
        cursor.execute(sql_create_ventas_table)
        cursor.execute(sql_create_detalle_venta_table)
        conn.commit()
    except sqlite3.Error as e:
        print(f"Error al crear tablas: {e}")


def execute_dynamic_query(conn, sql_query):
    """
    Ejecuta una consulta SQL dinámica generada por la IA.
    Añade un control de seguridad para permitir solo consultas SELECT.
    """
    cleaned_query = sql_query.strip().upper()
    
    # ------------------ CÓDIGO DE SEGURIDAD (SELECT ONLY) ------------------
    # 1. Bloquear comandos que no sean SELECT
    if not cleaned_query.startswith("SELECT"):
        return None, None, "ERROR DE SEGURIDAD: Solo se permiten consultas de tipo SELECT."
        
    # 2. Bloquear comandos múltiples
    # Revisa si hay más de un punto y coma después de eliminar el potencial punto y coma final
    if cleaned_query.replace(";", "", 1).count(';') > 0:
         return None, None, "ERROR DE SEGURIDAD: Se detectaron múltiples comandos en la consulta."
    # ------------------------------------------------------------------
    
    try:
        cur = conn.cursor()
        cur.execute(sql_query)
        
        # Si la consulta fue SELECT, obtenemos resultados
        if cur.description:
            columns = [description[0] for description in cur.description]
            rows = cur.fetchall()
            return columns, rows, None
        else:
            # Caso de un comando no SELECT que pasó el filtro de seguridad (ej. PRAGMA)
            return None, None, "Consulta ejecutada sin resultados (no es SELECT)."
    
    except sqlite3.OperationalError as e:
        # Captura errores de sintaxis SQL, columna/tabla inexistente
        return None, None, str(e)
    except Exception as e:
        # Otros errores inesperados
        return None, None, f"Error desconocido al ejecutar SQL: {e}"


def main_db_setup():
    """Configura la conexión y crea las tablas."""
    conn = create_connection()
    if conn:
        create_tables(conn)
        # Nota: La función seed_data se definirá en el Paso 3
        # seed_data(conn) 
        # conn.close()
        return conn

# Si ejecutas main_db_setup() en este archivo, se debe crear la DB.
if __name__ == '__main__':
    conn = main_db_setup()
    if conn:
        print("Base de datos y tablas iniciales creadas exitosamente.")
        conn.close()