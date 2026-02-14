import os
from supabase import create_client, Client

# --- CONFIGURACIÓN ACTUALIZADA ---
SUPABASE_URL = "https://kebpamfydhnxeaeegulx.supabase.co"
# Esta es la clave 'anon' que me pasaste
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtlYnBhbWZ5ZGhueGVhZWVndWx4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjY4ODExNzUsImV4cCI6MjA4MjQ1NzE3NX0.CIeBgEwmhbd8f-NYgdpebokVenaA12qnsNyLFYVP51M"

def diagnostico_elena():
    try:
        # Inicializar cliente con la nueva clave
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        print("\n" + "="*45)
        print("🩺 TEST DE CONEXIÓN - ELENA AI")
        print("="*45)

        # 1. Prueba de Conexión Básica
        try:
            # Intentamos leer la tabla de suscripciones (si el RLS lo permite)
            res = supabase.table('suscripciones').select("*").limit(1).execute()
            print(f"✅ CONEXIÓN: Exitosa. La llave es válida.")
        except Exception as e:
            if "401" in str(e):
                print(f"❌ ERROR 401: La llave no es válida o expiró.")
            elif "403" in str(e) or "PGRST116" in str(e):
                print(f"⚠️ RLS ACTIVO: La llave conecta, pero el RLS bloqueó la lectura.")
                print("   (Esto es bueno: la seguridad funciona, pero para el bot usaremos la service_role)")
            else:
                print(f"❌ ERROR: {e}")

        # 2. Prueba de la función Incrementar (la que parcheamos)
        print("\n--- Verificando Funciones SQL ---")
        try:
            supabase.rpc('incrementar_consulta', {'farmacia_email': 'test@farmacia.com'}).execute()
            print("✅ FUNCIÓN 'incrementar_consulta': Accesible.")
        except Exception as e:
            print(f"ℹ️  FUNCIÓN: No se ejecutó (Normal con llave anon).")

        print("="*45)
        print("💡 PRÓXIMO PASO: Si ves 'CONEXIÓN: Exitosa', ya")
        print("   podemos cargar el Excel en app.py.")
        print("="*45 + "\n")

    except Exception as e:
        print(f"\n❌ ERROR CRÍTICO: {e}")

if __name__ == "__main__":
    diagnostico_elena()