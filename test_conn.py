import os, psycopg2

db_url = os.environ.get("DATABASE_URL")
print("Usando DATABASE_URL:", db_url)

try:
    conn = psycopg2.connect(db_url, sslmode="require")
    print("✅ Conexión exitosa a PostgreSQL")
    conn.close()
except Exception as e:
    print("❌ Error de conexión:", e)
