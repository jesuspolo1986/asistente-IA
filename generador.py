import pandas as pd

# Creamos los datos "sucios"
data = {
    "ARTICULO": ["ATAMEL ADULTO 650MG", "ACETAMINOFEN GENERICO", "VITAMINA C MK", "IBUPROFENO 400MG"],
    "P.V.P (REF)": ["Ref 2,50 $", "$ 1.15", "4,20 USD", "  3.00  "],
    "EXISTENCIA": ["12", "100", "5", "20"]
}

df_datos = pd.DataFrame(data)

# Creamos la "basura" del encabezado
basura = [
    ["FARMACIA LA BENDICIÓN C.A.", "", ""],
    ["RIF: J-12345678-0", "FECHA: 23/01/2026", ""],
    ["REPORTE DE INVENTARIO CAÓTICO", "", ""],
    ["", "", ""] # Fila vacía
]
df_basura = pd.DataFrame(basura)

# Unimos todo: la basura arriba y los datos abajo
# Nota: Ignoramos los índices para que parezca un Excel real
with pd.ExcelWriter("inventario_sucio.xlsx") as writer:
    df_basura.to_excel(writer, index=False, header=False)
    df_datos.to_excel(writer, index=False, startrow=4) # Empezamos en la fila 5

print("✅ Archivo 'inventario_sucio.xlsx' creado con éxito.")