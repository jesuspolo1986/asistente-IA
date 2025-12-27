import os
from mistralai import Mistral

# Configura tu clave manualmente para la prueba
api_key = "0dy1xuNg30CNZ32uAsPATlVHKKm5NBxn" 
client = Mistral(api_key=api_key)

try:
    response = client.chat.complete(
        model="mistral-tiny", # El modelo más rápido para pruebas
        messages=[{"role": "user", "content": "Hola, ¿estás funcionando?"}]
    )
    print("✅ Conexión exitosa:")
    print(response.choices[0].message.content)
except Exception as e:
    print(f"❌ Error de conexión: {e}")