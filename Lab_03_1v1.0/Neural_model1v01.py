import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

penguins = sns.load_dataset("penguins")

print(penguins.head(5))
print(penguins.info())
print("\nMissing values:")
print(penguins.isna().sum())
print(penguins["species"].value_counts())
sns.pairplot(penguins, hue="species", corner=True)
plt.show()