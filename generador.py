import pandas as pd

# ARCHIVO A: Retail (Tiendas y Ventas)
retail_data = {
    'Tienda': ['Norte', 'Sur', 'Este', 'Oeste', 'Centro'],
    'SKU': ['LAP-001', 'MOU-99', 'KEY-12', 'MON-45', 'SUR-01'],
    'Ventas_Netas': [15200.50, 8900.00, 12450.75, 21000.00, 5600.20]
}
pd.DataFrame(retail_data).to_csv('retail_test.csv', index=False)

# ARCHIVO B: Recursos Humanos (Nómina)
rrhh_data = {
    'Empleado': ['Laura Cano', 'Pedro Picapiedra', 'Marta Sánchez', 'Juan Soler'],
    'Departamento': ['Sistemas', 'Ventas', 'Sistemas', 'Marketing'],
    'Sueldo': [3500, 2800, 3600, 2200],
    'Horas_Extra': [10, 5, 12, 0]
}
pd.DataFrame(rrhh_data).to_csv('rrhh_test.csv', index=False)

# ARCHIVO C: Logística (Transporte)
logistica_data = {
    'Ruta': ['Madrid-Barcelona', 'Valencia-Sevilla', 'Bilbao-Madrid'],
    'Conductor': ['Antonio G.', 'Josefa M.', 'Ricardo L.'],
    'Costo_Combustible': [450.20, 380.00, 210.50],
    'Kilometros': [620, 540, 400]
}
pd.DataFrame(logistica_data).to_csv('logistica_test.csv', index=False)

print("¡Archivos retail_test.csv, rrhh_test.csv y logistica_test.csv creados!")