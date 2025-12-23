import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

# Crear motor asincrónico con asyncpg
DATABASE_URL = os.environ.get("DATABASE_URL")
# Cambiar el esquema para asyncpg
DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

engine = create_async_engine(DATABASE_URL, echo=True)

# Función para ejecutar consultas dinámicas
async def execute_dynamic_query(query: str):
    async with engine.connect() as conn:
        result = await conn.execute(text(query))
        return result.fetchall()

# Crear tablas de ejemplo
async def create_tables():
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ventas (
                id SERIAL PRIMARY KEY,
                producto VARCHAR(100),
                cantidad INT,
                precio FLOAT
            )
        """))

#polo