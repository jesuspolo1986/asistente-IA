import pandas as pd
from sqlalchemy import create_engine
import os

def procesar_y_cargar_excel(file_path):
    DATABASE_URL = os.environ.get("DATABASE_URL")
    if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    
    if not DATABASE_URL:
        return False, "Error de configuración de BD", None

    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    
    try:
        # 1. Lectura con detección automática
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path, sep=None, engine='python', encoding='utf-8-sig')
        else:
            df = pd.read_excel(file_path)
        
        # 2. Normalización de columnas
        df.columns = [str(c).strip().lower().replace(' ', '_') for c in df.columns]

        # --- NUEVA LÓGICA: CÁLCULO DE KPIs PARA EL DASHBOARD ---
        # Buscamos columnas clave (total, vendedor, producto, unidades)
        # Adaptamos según los nombres que suelen venir en tus archivos
        total_ventas = df['total'].sum() if 'total' in df.columns else 0
        
        mejor_vendedor = "N/A"
        if 'vendedor' in df.columns and 'total' in df.columns:
            mejor_vendedor = df.groupby('vendedor')['total'].sum().idxmax()
            
        producto_top = "N/A"
        if 'producto' in df.columns and 'total' in df.columns:
            producto_top = df.groupby('producto')['total'].sum().idxmax()
            
        unidades_totales = len(df) # O suma de columna 'cantidad' si existe
        if 'cantidad' in df.columns:
            unidades_totales = int(df['cantidad'].sum())

        summary = {
            "total_ventas": f"${total_ventas:,.2f}",
            "mejor_vendedor": str(mejor_vendedor),
            "producto_top": str(producto_top),
            "unidades": str(unidades_totales)
        }
        # ------------------------------------------------------

        # 3. Inserción en DB
        with engine.begin() as connection:
            df.to_sql('ventas', con=connection, if_exists='append', index=False, method='multi')
        
        return True, f"Se sincronizaron {len(df)} registros.", summary
    
    except Exception as e:
        return False, f"Error: {str(e)}", None