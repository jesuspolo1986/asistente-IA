import requests
from bs4 import BeautifulSoup
import urllib3

# Desactivamos alertas de certificados para que la conexión sea limpia
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def probar_extraccion_bcv():
    url = "https://www.bcv.org.ve/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
    }

    print("🔎 Intentando conectar con el portal del BCV...")
    
    try:
        # 1. Realizar la petición
        response = requests.get(url, headers=headers, verify=False, timeout=10)
        
        if response.status_code == 200:
            # 2. Parsear el HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 3. Localizar el contenedor específico del Dólar
            # El BCV usa un div con id="dolar" y dentro un strong con el valor
            contenedor_dolar = soup.find('div', id='dolar')
            
            if contenedor_dolar:
                valor_texto = contenedor_dolar.find('strong').text.strip()
                print(f"✅ Texto encontrado en la web: '{valor_texto}'")
                
                # 4. Convertir a formato numérico (Python usa puntos, no comas)
                tasa_numerica = float(valor_texto.replace(',', '.'))
                
                print("-" * 30)
                print(f"🚀 RESULTADO PARA ELENA: {tasa_numerica}")
                print(f"💰 Un producto de 10$ costaría: {tasa_numerica * 10:.2f} Bs.")
                print("-" * 30)
            else:
                print("❌ No se encontró el contenedor 'dolar' en la página.")
        else:
            print(f"❌ Error de conexión. Código de estado: {response.status_code}")

    except Exception as e:
        print(f"❌ Ocurrió un error inesperado: {e}")

if __name__ == "__main__":
    probar_extraccion_bcv()