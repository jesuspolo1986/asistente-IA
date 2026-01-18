from pyDolarVenezuela.pages import AlCambio
from pyDolarVenezuela import Monitor

def probar_alcambio_final():
    print("📡 Consultando AlCambio con pyDolarVenezuela...")
    
    try:
        # Iniciamos el monitor
        monitor = Monitor(AlCambio, 'USD')
        
        # Como es una lista, vamos a buscar el objeto que se llame 'AlCambio'
        monitores = monitor.get_all_monitors()
        
        tasa_encontrada = None
        
        for m in monitores:
            # Imprimimos para que veas qué hay dentro
            print(f"🔍 Encontrado: {m.title} - Precio: {m.price}")
            
            # El título suele ser "AlCambio"
            if "AlCambio" in m.title or "oficial" in m.title.lower():
                tasa_encontrada = m.price
                break
        
        if tasa_encontrada:
            print(f"\n✅ TASA DETECTADA PARA ELENA: {tasa_encontrada}")
            return tasa_encontrada
        else:
            # Si no lo encuentra por nombre, tomamos el primero de la lista
            tasa_encontrada = monitores[0].price
            print(f"\n✅ TASA (Primer Monitor): {tasa_encontrada}")
            return tasa_encontrada

    except Exception as e:
        print(f"❌ Error al procesar la lista: {e}")

if __name__ == "__main__":
    probar_alcambio_final()