import pandas as pd
import random
from datetime import datetime, timedelta

# Configuración de datos ficticios
productos = {
    'Laptop Pro': 1200, 'Monitor 4K': 350, 'Teclado Mecánico': 80, 
    'Mouse Gamer': 50, 'Silla Ergonómica': 250, 'Headset Wireless': 120
}
categorias = ['Electrónica', 'Accesorios', 'Muebles']
vendedores = ['Carlos Ruiz', 'Ana López', 'Beatriz Peña', 'Diego Sosa']

data = []

for i in range(1, 101):  # Generamos 100 ventas
    producto = random.choice(list(productos.keys()))
    cantidad = random.randint(1, 5)
    precio = productos[producto]
    vendedor = random.choice(vendedores)
    fecha = datetime(2025, 12, 1) + timedelta(days=random.randint(0, 25))
    
    data.append([
        fecha.strftime('%Y-%m-%d'),
        vendedor,
        producto,
        cantidad,
        precio,
        cantidad * precio
    ])

df = pd.DataFrame(data, columns=['Fecha', 'Vendedor', 'Producto', 'Cantidad', 'Precio_Unitario', 'Total'])
df.to_csv('ventas_prueba.csv', index=False)
print("¡Archivo ventas_prueba.csv creado con éxito!")