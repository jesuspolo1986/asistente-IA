import pandas as pd
from sqlalchemy import create_engine, text
import os

def procesar_y_cargar_excel(file_path):
    # 1. Configuración de la URL (Mantenemos tu lógica que es correcta)
    DATABASE_URL = os.environ.get("DATABASE_URL")
    if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    
    if not DATABASE_URL:
        return False, "Error: DATABASE_URL no configurada en el servidor."

    # Usamos pool_pre_ping para evitar desconexiones en Render
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    
    try:
        # 2. Lectura inteligente del archivo
        if file_path.endswith('.csv'):
            # El encoding 'latin1' o 'utf-8' ayuda con tildes y ñ
            df = pd.read_csv(file_path, encoding='utf-8')
        else:
            df = pd.read_excel(file_path)
        
        # 3. Limpieza profunda de columnas (Tu lógica + strip para quitar espacios invisibles)
        df.columns = [str(c).lower().replace(' ', '_').strip() for c in df.columns]

        # 4. Inserción en la base de datos
        # Creamos una conexión explícita para asegurar el cierre del proceso
        with engine.begin() as connection:
            df.to_sql(
                'ventas_externas', 
                con=connection, 
                if_exists='append', 
                index=False,
                method='multi' # Esto acelera la carga en PostgreSQL
            )
        
        return True, f"¡Éxito! Se sincronizaron {len(df)} registros correctamente."
    
    except Exception as e:
        # Si el error es por falta de una librería específica de Excel
        if "openpyxl" in str(e).lower():
            return False, "Error técnico: Falta la librería openpyxl en el servidor."
        return False, f"Error al procesar: {str(e)}"