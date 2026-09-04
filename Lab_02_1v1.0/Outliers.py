import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import datetime as dt

#fase 1

transacciones = pd.read_csv('ecommerce_transactions.csv')
transacciones.head(5)
transacciones.info()

#fase 2

transacciones.isnull().sum()
transacciones = transacciones.dropna()
sns.boxplot(y=transacciones['Quantity'])
plt.show()
Q1 = transacciones['Quantity'].quantile(0.25)
Q3 = transacciones['Quantity'].quantile(0.75)
IQR = Q3 - Q1
IQR
limite_inferior = Q1 - 1.5 * IQR
limite_superior = Q3 + 1.5 * IQR
outliers = (transacciones['Quantity'] < limite_inferior) | (transacciones['Quantity'] > limite_superior)
transacciones = transacciones[~outliers]
sns.boxplot(y=transacciones['Quantity'])
transacciones = transacciones[transacciones['Quantity'] > 0]
sns.boxplot(y=transacciones['Quantity'])

#fase 3

transacciones['Revenue'] = transacciones['Price'] * transacciones['Quantity']
transacciones.head(5)
productos_agrupados = transacciones.groupby('ProductName')
suma_cantidades_por_producto = productos_agrupados['Quantity'].sum()
productos_mas_vendidos = suma_cantidades_por_producto.sort_values(ascending=False)
productos_mas_vendidos.head(10)
plt.figure(figsize=(12, 6))
sns.barplot(x=productos_mas_vendidos.head(10), y=productos_mas_vendidos.head(10).index, palette='viridis')
plt.title('Top 10 Productos más Vendidos')
plt.xlabel('Cantidad')
plt.ylabel('Producto')
plt.show()
productos_agrupados = transacciones.groupby('ProductName')
suma_ingresos_por_producto = productos_agrupados['Revenue'].sum()
productos_mas_ingresos = suma_ingresos_por_producto.sort_values(ascending=False)
productos_mas_ingresos.head(10)
plt.figure(figsize=(12, 6))
sns.barplot(x=productos_mas_ingresos.head(10), y=productos_mas_ingresos.head(10).index, palette='viridis')
plt.title('Top 10 Productos con más Ingresos')
plt.xlabel('Ingresos')
plt.ylabel('Producto')
plt.show()
transacciones['Date'] = pd.to_datetime(transacciones['Date'], format='%m/%d/%Y')
transacciones['Month'] = transacciones['Date'].dt.month
ventas_por_mes = transacciones.groupby('Month')['Revenue'].sum()
plt.figure(figsize=(12, 6))
sns.barplot(x=ventas_por_mes.index, y=ventas_por_mes.values, palette='viridis')
plt.title('Ganancias por Mes')
plt.xlabel('Mes')
plt.ylabel('Ganancias')
plt.show()
transacciones['DayOfWeek'] = transacciones['Date'].dt.day_name()
ventas_por_dia_semana = transacciones['DayOfWeek'].value_counts()
plt.figure(figsize=(12, 6))
sns.barplot(x=ventas_por_dia_semana.index, y=ventas_por_dia_semana.values, palette='viridis')
plt.title('Ventas por Día de la Semana')
plt.xlabel('Día de la Semana')
plt.ylabel('Ventas')
plt.show()

