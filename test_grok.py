import os
import base64
from groq import Groq

# 1. Configura tu API KEY (Obtenla gratis en console.groq.com)
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

def encode_image(image_path):
    """Convierte la imagen a base64 para enviarla a la IA"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def analizar_recipe(ruta_imagen):
    # Convertimos la foto del récipe
    base64_image = encode_image(ruta_imagen)

    # Llamada al modelo de visión de Groq (Llama 3.2 Vision)
    completion = client.chat.completions.create(
        model="llama-3.2-11b-vision-preview",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text", 
                        "text": """Actúa como un farmacéutico experto. 
                        Analiza la imagen de este récipe médico y extrae:
                        - Nombre del medicamento.
                        - Concentración (mg, ml, etc).
                        - Indicación (opcional).
                        
                        Responde estrictamente en formato JSON."""
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}",
                        },
                    },
                ],
            }
        ],
        temperature=0.1, # Baja temperatura para mayor precisión
        response_format={"type": "json_object"}
    )

    return completion.choices[0].message.content

# --- EJECUCIÓN DE PRUEBA ---
if __name__ == "__main__":
    # Coloca una foto de un récipe llamada 'recipe.jpg' en la misma carpeta
    archivo = "recipe.jpg" 
    
    if os.path.exists(archivo):
        print("Analizando récipe... espera un segundo.")
        resultado = analizar_recipe(archivo)
        print("\n--- RESULTADO DE ELENA ---")
        print(resultado)
    else:
        print(f"Error: No encontré el archivo {archivo}")