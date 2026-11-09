import pandas as pd
d = pd.read_csv('data/processed/batches/batch_01.csv')
print('All columns:', d.columns.tolist())
print()
print('First 5 rows:')
print(d.head().to_string())
