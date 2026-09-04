import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

titanic = pd.read_csv('titanic.csv')

# Survive by sex
survived_by_sex = titanic.groupby('Sex')['Survived'].mean().reset_index()

plt.figure(figsize=(6, 4))
sns.barplot(data=survived_by_sex, x='Sex', y='Survived', palette='pastel')
plt.title('Tasa de supervivencia por sexo')
plt.xlabel('Sexo')
plt.ylabel('Proporción de sobrevivientes')
plt.ylim(0, 1)
plt.show()

# Survive by class

survived_by_class = titanic.groupby('Pclass')['Survived'].mean().reset_index()

plt.figure(figsize=(6, 4))
sns.barplot(data=survived_by_class, x='Pclass', y='Survived', palette='pastel')
plt.title('Tasa de supervivencia por clase de pasajero')
plt.xlabel('Clase (Pclass)')
plt.ylabel('Proporción de sobrevivientes')
plt.ylim(0, 1)
plt.show()