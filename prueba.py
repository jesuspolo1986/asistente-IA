import os
import google.genai as genai

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

print("📡 Modelos disponibles:")
for m in client.models.list():
    print(m.name)   # Solo imprime el nombre del modelo
