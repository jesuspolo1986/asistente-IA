import pandas as pd

# Datos con unidades médicas y precios de prueba
data = {
    "PRODUCTO": [
        "ACETAMINOFEN 500MG", 
        "JARABE PARA LA TOS 120ML", 
        "CREMA DERMICA 30GR", 
        "VITAMINA C 1G",
        "TRATAMIENTO ESPECIALIZADO"
    ],
    "PRECIO_USD": [
        "1.50", 
        "8.20", 
        "5.00", 
        "2.00", 
        "25.00" # Este servirá para probar los miles en Bolívares
    ],
    "STOCK": [50, 20, 15, 40, 5]
}

df = pd.DataFrame(data)

# Añadimos basura en el encabezado como un Excel real de farmacia
basura = [
    ["DROGUERIA ELENA TEST C.A.", "", ""],
    ["INVENTARIO DE PRUEBA DE UNIDADES", "", ""],
    ["", "", ""]
]
df_basura = pd.DataFrame(basura)

with pd.ExcelWriter("inventario_unidades.xlsx") as writer:
    df_basura.to_excel(writer, index=False, header=False)
    df.to_excel(writer, index=False, startrow=3)

print("✅ Archivo 'inventario_unidades.xlsx' creado.")