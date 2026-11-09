# -*- coding: utf-8 -*-
import time
import warnings
import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
import requests
import yfinance as yf
from joblib import Parallel, delayed


class analiseFundamental():
    def __init__(self):
        self.dict_empresas = []

    def run(self,empresa, inicio, fim):
        url = "https://investnews.com.br/financas/veja-a-lista-completa-dos-bdrs-disponiveis-para-pessoas-fisicas-na-b3/"
        r = requests.get(url)
        html = r.text
        df_names_tickers = pd.read_html(html, header=0)[0]
        dados_serie = self.lista(dict_empresa=empresa, inicio=inicio, fim=fim)
        self.view(dados_serie, df_names_tickers)

    def view(self, dados_serie, df_names_tickers):
        df_names_tickers.head(10)
        warnings.filterwarnings("ignore")
        plt.style.use('fivethirtyeight')
        matplotlib.rcParams['axes.labelsize'] = 14
        matplotlib.rcParams['xtick.labelsize'] = 12
        matplotlib.rcParams['ytick.labelsize'] = 12
        # dados_grafico = [go.Scatter(x=dados_serie.index, y=dados_serie['Close'])]
        # py.plot(dados_grafico)
        # nome das colunas ['Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']
        df = dados_serie.drop(['Open', 'High', 'Low', 'Volume'], axis=1)
        df.plot(figsize=(19, 4))
        plt.show()
        dados_serie = dados_serie.head(-10)
        print(dados_serie)

    def lista(self, dict_empresa, inicio, fim):
        dados_serie = yf.download(f'{dict_empresa}', start=inicio, end=fim)
        return dados_serie

if __name__ == "__main__":
    af = analiseFundamental()
    #insira as empresas que queira analisar
    # ou fundos imobiliarios
    empresa = ["PETR4.SA", "BBAS3","MXRF11","XPLG11", "BCFF11", "ITUBA4"]

    def executor(x):
        af.run(x, inicio="2021-01-01", fim="2022-06-04")

    Parallel(n_jobs=-1)(delayed(executor)(x) for x in empresa)
    print(f'Demorou {time.thread_time()}')


