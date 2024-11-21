import pandas as pd

# Carregar o CSV
df = pd.read_csv('../dados/csv/15-11-2024/stock_data_BTC-BRL.csv')

# Corrigir o formato dos números (remover pontos e trocar vírgulas por pontos)
df['Valor'] = df['Valor'].str.replace('.', '').str.replace(',', '.').astype(float)

# Converter a coluna de datas para datetime
df['Data_minute'] = pd.to_datetime(df['Data_minute'])

# Definir a coluna de datas como índice
df.set_index('Data_minute', inplace=True)

print(df.head())
