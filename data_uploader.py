import pandas as pd
from sqlalchemy import create_engine, text
import os

def procesar_y_cargar_excel(file_path):
    # 1. Configuración de la URL (Aseguramos el dialecto postgresql://)
    DATABASE_URL = os.environ.get("DATABASE_URL")
    if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    
    if not DATABASE_URL:
        return False, "Error: DATABASE_URL no configurada en el servidor."

    # pool_pre_ping es vital para mantener la conexión viva en Koyeb/PostgreSQL
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    
    try:
        # 2. Lectura inteligente con detección de separador
        if file_path.endswith('.csv'):
            # sep=None y engine='python' detectan automáticamente si es , o ;
            # encoding='latin1' suele ser más seguro para archivos creados en Excel/Windows
            df = pd.read_csv(file_path, sep=None, engine='python', encoding='utf-8-sig')
        else:
            # Para archivos .xlsx
            df = pd.read_excel(file_path)
        
        # 3. Limpieza profunda de nombres de columnas
        # Quitamos espacios al inicio/final, pasamos a minúsculas y reemplazamos espacios por guiones bajos
        df.columns = [str(c).strip().lower().replace(' ', '_') for c in df.columns]

        # 4. Inserción optimizada en la base de datos
        with engine.begin() as connection:
            df.to_sql(
                'ventas', # Usamos la tabla 'ventas' que ya vimos en tus logs
                con=connection, 
                if_exists='append', 
                index=False,
                method='multi' # Acelera la carga masiva en la nube
            )
        
        return True, f"¡Éxito! Se sincronizaron {len(df)} registros correctamente."
    
    except pd.errors.ParserError:
        return False, "Error de formato: El CSV tiene una estructura irregular. Revisa las comas o puntos y comas."
    except Exception as e:
        if "openpyxl" in str(e).lower():
            return False, "Error técnico: Falta la librería 'openpyxl' en el servidor."
        return False, f"Error crítico: {str(e)}"