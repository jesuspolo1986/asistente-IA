import pandas as pd
from sqlalchemy import create_engine
import os

def procesar_y_cargar_excel(file_path):
    # Obtenemos la URL de la base de datos de Render
    DATABASE_URL = os.environ.get("DATABASE_URL")
    if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    
    engine = create_engine(DATABASE_URL)
    
    try:
        # 1. Leer el archivo (funciona con CSV o Excel)
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)
        
        # 2. Limpieza básica de nombres de columnas (quitar espacios, minúsculas)
        df.columns = [c.lower().replace(' ', '_') for c in df.columns]
        
        # 3. Insertar en la tabla de Ventas (o una tabla temporal)
        # Nota: 'if_exists=append' agrega los datos a lo que ya hay
        df.to_sql('ventas_externas', engine, if_exists='append', index=False)
        
        return True, f"¡Éxito! Se cargaron {len(df)} registros."
    
    except Exception as e:
        return False, f"Error al procesar: {str(e)}"