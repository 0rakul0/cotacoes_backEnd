import asyncio
import time

import pandas as pd
from datetime import datetime, time as dt_time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from matplotlib import pyplot as plt
import numpy as np
import os
from plyer import notification
from concurrent.futures import ThreadPoolExecutor

class Cotacoes:
    def __init__(self, stock_csv_path):
        self.stock_csv_path = stock_csv_path

    def run(self, ticker):
        # Inicialização do navegador (headless)
        chrome_options = Options()
        # chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        driver = webdriver.Chrome(options=chrome_options)
        driver.get(f"https://www.google.com/finance/quote/{ticker}")
        time.sleep(4)

        try:
            print(f"Iniciando monitoramento para {ticker}...")
            if self.is_market_open():
                data_minute = datetime.now().strftime("%Y-%m-%d %H:%M")
                self.start(ticker, driver, data_minute)
                self.graph_price(ticker)
            else:
                print(f"Mercado fechado para {ticker}.")
        except Exception as e:
            print(f"Erro ao processar o ticker {ticker}: {e}")
        finally:
            self.close_browser(driver)
            print(f"Navegador fechado para {ticker}.")

    def start(self, ticker, driver, data_minute):
        try:
            price_element = driver.find_element("xpath", '//*[@class="YMlKec fxKbKc"]')
            price = price_element.text

            arquivo = f'{self.stock_csv_path}_{str(ticker).split(":")[0]}.csv'
            df_stock = pd.DataFrame([{
                'Data_minute': data_minute,
                'Valor': price,
                'Ticker': ticker
            }])
            if os.path.exists(arquivo):
                df_stock.to_csv(arquivo, mode='a', index=False, header=False)
            else:
                df_stock.to_csv(arquivo, index=False)
        except Exception as e:
            print(f"Erro ao capturar dados para {ticker}: {e}")
            driver.refresh()

    def graph_price(self, ticker):
        """Gera e salva gráficos dos preços agrupados a cada 5 minutos para cada ticker."""
        img_folder = "../dados/img"
        os.makedirs(img_folder, exist_ok=True)
        arquivo = f'{self.stock_csv_path}_{str(ticker).split(":")[0]}.csv'

        if os.path.exists(arquivo):
            df = pd.read_csv(arquivo)
            df["Valor"] = pd.to_numeric(df["Valor"].str.replace(".", "").str.replace(",", ".").str.replace("R$", ""),
                                        errors='coerce')
            df.dropna(subset=["Valor"], inplace=True)
            df["Data_minute"] = pd.to_datetime(df["Data_minute"], errors='coerce')
            df.set_index("Data_minute", inplace=True)

            # Configura o gráfico
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
            ultimo_valor = df["Valor"].iloc[-1]

            if maxima == ultimo_valor or minima == ultimo_valor:
                self.notifica(media, maxima, minima, ultimo_valor, ticker)

            plt.axhline(maxima, color="green", linestyle="--", label=f"Máxima: {maxima:.2f}")
            plt.axhline(minima, color="red", linestyle="--", label=f"Mínima: {minima:.2f}")
            plt.tight_layout()

            img_path = os.path.join(img_folder, f"{str(ticker).split(':')[0]}.png")
            plt.savefig(img_path)
            plt.close()

    def notifica(self, media, maxima, minima, atual, ticker):
        if maxima == atual:
            notification.notify(
                title="Mercado Atual",
                message=f"Ticker {ticker} >> Máxima {maxima} a média está em {media:.2f}",
                timeout=30
            )
        elif minima == atual:
            notification.notify(
                title="Mercado Atual",
                message=f"Ticker {ticker} >> Mínima de {minima} a média está em {media:.2f}",
                timeout=30
            )

    def is_market_open(self):
        """Verifica se o mercado está aberto (segunda a sexta, entre 10:00 e 18:20)."""
        now = datetime.now()
        return now.weekday() < 5 and dt_time(10, 0) <= now.time() <= dt_time(18, 20)

    def close_browser(self, driver):
        """Fecha o navegador."""
        driver.quit()


async def process_ticker(ticker, cotacoes, executor, intervalo=60):
    """Processa o ticker a cada intervalo."""
    while True:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(executor, cotacoes.run, ticker)
        await asyncio.sleep(intervalo)


async def main():
    dia = datetime.today().strftime("%d-%m-%Y")
    os.makedirs(f"../dados/csv/{dia}", exist_ok=True)
    stock_csv_path = f"../dados/csv/{dia}/stock_data"
    cotacoes = Cotacoes(stock_csv_path)

    TICKERS = ["BTC-BRL"]
    max_threads = 4  # Defina o limite de threads conforme sua máquina
    intervalo = 60  # Intervalo em segundos

    executor = ThreadPoolExecutor(max_threads)
    tasks = [process_ticker(ticker, cotacoes, executor, intervalo) for ticker in TICKERS]

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
