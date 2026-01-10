import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Analista Pro - Monitor", layout="wide")

# --- CONEXIÓN ---
# Usamos el puerto 443 para intentar saltar bloqueos de firewall
DB_URL = "postgresql://postgres.kebpamfydhnxeaeegulx:YNjscilzeWI9LbzR@aws-0-sa-east-1.pooler.supabase.com:443/postgres?sslmode=require"

@st.cache_resource
def get_engine():
    # connect_timeout=5 evita que la página se quede en blanco si el puerto está bloqueado
    return create_engine(DB_URL, connect_args={'connect_timeout': 5})

def cargar_datos():
    engine = get_engine()
    with engine.connect() as conn:
        users = pd.read_sql(text("SELECT email, fecha_vencimiento, creditos_usados FROM suscripciones"), conn)
        logs = pd.read_sql(text("SELECT email, accion, detalle, fecha FROM logs_actividad ORDER BY fecha DESC"), conn)
    return users, logs

# --- INTERFAZ ---
st.title("🚀 Analista Pro: Torre de Control")
st.markdown(f"*Estado del sistema a las: {datetime.now().strftime('%H:%M:%S')}*")

try:
    with st.spinner("⏳ Conectando con Supabase..."):
        users, logs = cargar_datos()
    
    st.success("✅ Conexión establecida")
    
    # KPIs
    c1, c2 = st.columns(2)
    c1.metric("Usuarios Totales", len(users))
    c2.metric("Registros de Actividad", len(logs))
    
    # Mostrar tablas
    st.subheader("👥 Usuarios")
    st.dataframe(users, use_container_width=True)
    
    st.subheader("📜 Actividad Reciente")
    st.dataframe(logs.head(20), use_container_width=True)

except Exception as e:
    st.error("❌ No se pudo obtener la información de la base de datos.")
    st.warning(f"Detalle técnico: {e}")
    st.info("💡 Sugerencia: Si el error dice 'Timeout', intenta conectar tu PC al internet de tu CELULAR para descartar bloqueos de tu proveedor de WiFi.")

st.markdown("---")