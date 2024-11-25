import time
import pandas as pd
from datetime import datetime, time as dt_time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from matplotlib import pyplot as plt
import numpy as np
import os
from plyer import notification
from joblib import Parallel, delayed


class cotacoes():
    def run(self, ticker):
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        driver = webdriver.Chrome(options=chrome_options)

        driver.get(f"https://www.google.com/finance/quote/{ticker}")

        try:
            print(f"Iniciando o monitoramento... ticker {ticker}")
            if self.is_market_open():
                os.makedirs(f"../dados/csv/{dia}", exist_ok=True)
                self.STOCK_CSV_PATH = f"../dados/csv/{dia}/stock_data"
                data_minute = datetime.now().strftime("%Y-%m-%d %H:%M")
                self.start(ticker, driver, data_minute)
                self.graph_price(ticker)
            else:
                print("Fora do horário de mercado. Aguardando para retomar...")
        except KeyboardInterrupt:
            print(f"Encerrando o monitoramento... ticker {ticker}")
        finally:
            self.close_browser(driver)
            print(f"Navegador fechado para {ticker}.")

    def start(self, ticker, driver, data_minute):
        try:
            price_element = driver.find_element("xpath", '//*[@class="YMlKec fxKbKc"]')
            price = price_element.text

            arquivo = f'{self.STOCK_CSV_PATH}_{str(ticker).split(":")[0]}.csv'
            df_stock = pd.DataFrame([{
                'Data_minute': data_minute,
                'Valor': price,
                'Ticker': ticker
            }])
            if os.path.exists(arquivo):
                df_stock.to_csv(arquivo, mode='a', index=False, header=False)
            else:
                df_stock.to_csv(arquivo, index=False)
        except:
            driver.refresh()
            pass

    def notifica(self, media, maxima, minima, atual, ticker):
        if maxima == atual:
            notification.notify(
                title="Mercado Atual",
                message=f"Ticker {ticker} >> Máxima {maxima} a media está em {media:.2f}",
                timeout=30
            )
        elif minima == atual:
            notification.notify(
                title="Mercado Atual",
                message=f"Ticker {ticker} >> Mínima de {minima} a media está em {media:.2f}",
                timeout=30
            )

    def graph_price(self, ticker):
        """Função para gerar e salvar gráficos dos preços agrupados a cada 5 minutos para cada ticker."""
        img_folder = "../dados/img"
        os.makedirs(img_folder, exist_ok=True)
        arquivo = f'{self.STOCK_CSV_PATH}_{str(ticker).split(":")[0]}.csv'

        if os.path.exists(arquivo):
            df = pd.read_csv(arquivo)
            df["Valor"] = pd.to_numeric(df["Valor"].str.replace(".", "").str.replace(",", ".").str.replace("R$", ""),
                                        errors='coerce')
            df.dropna(subset=["Valor"], inplace=True)
            df["Data_minute"] = pd.to_datetime(df["Data_minute"], errors='coerce')
            df.set_index("Data_minute", inplace=True)

            plt.figure(figsize=(10, 6))
            plt.plot(df.index, df["Valor"], label=ticker)
            plt.title(f"Variação dos Preços de {ticker}")
            plt.xlabel("Data e Hora")
            plt.ylabel("Preço Médio (R$)")
            plt.legend()
            plt.xticks(rotation=45)

            maxima = df["Valor"].max()
            minima = df["Valor"].min()
            media = df["Valor"].mean()

            if maxima == df["Valor"].iloc[-1] or minima == df["Valor"].iloc[-1]:
                self.notifica(media, maxima, minima, df["Valor"].iloc[-1], ticker)

            plt.tight_layout()
            img_path = os.path.join(img_folder, f"{str(ticker).split(':')[0]}.png")
            plt.savefig(img_path)
            plt.close()

    def is_market_open(self):
        """Verifica se o mercado está aberto (segunda a sexta, entre 10:00 e 18:20)."""
        now = datetime.now()
        return now.weekday() < 5 and dt_time(10, 0) <= now.time() <= dt_time(18, 20)

    def close_browser(self, driver):
        """Fecha o navegador ao final do script."""
        driver.quit()


if __name__ == "__main__":
    dia = datetime.today().strftime("%d-%m-%Y")
    TICKERS = ["NVDC34:BVMF", "AAPL34:BVMF", "AMZO34:BVMF", "MXRF11:BVMF", "PETR4:BVMF"]

    c = cotacoes()

    while True:
        for ticker in TICKERS:
            c.run(ticker)
        time.sleep(50)