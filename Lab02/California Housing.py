import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from ProfileReport import ProfileReport

#fase 1

housing = pd.read_csv('housing.csv')
housing.head(15)
housing.describe()
housing.info()
housing.hist(figsize=(20, 15))

#fase 2

sns.scatterplot(x='longitude', y='latitude', data=housing)
sns.scatterplot(x='longitude', y='latitude', data=housing, alpha=0.1, hue='median_house_value')
sns.scatterplot(x='longitude', y='latitude', data=housing, alpha=0.1, hue='ocean_proximity')

#fase 3

profile = ProfileReport(housing, title='Reporte Perfilamiento de Datos', explorative=True)
profile.to_notebook_iframe()


