import os
import time
from datetime import datetime, time as dt_time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options


class Cotacoes_NVDC34:
    def __init__(self):
        self.ticker = "NVDC34:BVMF"
        dia = datetime.today().strftime("%d-%m-%Y")
        os.makedirs(f"../dados/csv/{dia}", exist_ok=True)
        self.STOCK_CSV_PATH = f"../dados/csv/{dia}/{self.ticker}"

    def run(self):
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        driver = webdriver.Chrome(options=chrome_options)

        try:
            print(f"Iniciando o monitoramento... ticker {self.ticker}")
            driver.get(f"https://www.google.com/finance/quote/{self.ticker}")
            if self.is_market_open():
                dia = datetime.today().strftime("%d-%m-%Y")
                os.makedirs(f"../dados/csv/{dia}", exist_ok=True)
                self.STOCK_CSV_PATH = f"../dados/csv/{dia}/stock_data"
                data_minute = datetime.now().strftime("%Y-%m-%d %H:%M")
                self.start(driver, data_minute)
            else:
                print("Fora do horário de mercado. Aguardando para retomar...")
        except KeyboardInterrupt:
            print(f"Encerrando o monitoramento... ticker {self.ticker}")
        finally:
            driver.quit()
            print("Navegador fechado.")

    def start(self, driver, data_minute):
        try:
            price_element = driver.find_element("xpath", '//*[@class="YMlKec fxKbKc"]')
            price = price_element.text

            arquivo = f'{self.STOCK_CSV_PATH}_{self.ticker.split(":")[0]}.csv'
            df_stock = pd.DataFrame([{
                'Data_minute': data_minute,
                'Valor': price,
                'Ticker': self.ticker
            }])
            if os.path.exists(arquivo):
                df_stock.to_csv(arquivo, mode='a', index=False, header=False)
            else:
                df_stock.to_csv(arquivo, index=False)
        except:
            driver.refresh()
            pass

    def is_market_open(self):
        now = datetime.now()
        return now.weekday() < 5 and dt_time(10, 0) <= now.time() <= dt_time(18, 0)
