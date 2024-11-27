from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import pandas as pd
import os
import logging
import time as t
from datetime import datetime, time
from cotacoes.grafico import gerar_grafico_html

# Configuração do logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Função global para gerenciar o navegador
driver = None

def start_browser():
    global driver
    if driver is None:
        logging.info("Iniciando o navegador Selenium...")
        chrome_options = Options()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--headless")
        driver = webdriver.Chrome(options=chrome_options)

def stop_browser():
    global driver
    if driver:
        logging.info("Encerrando o navegador Selenium...")
        driver.quit()
        driver = None

def save_data_to_csv(ticker, price):
    """
    Salva os dados coletados em um arquivo CSV organizado por data.

    Args:
        ticker (str): Nome do ativo.
        price (str): Preço coletado.
    """
    try:
        data_minute = datetime.now().strftime("%Y-%m-%d %H:%M")
        dia = datetime.today().strftime("%d-%m-%Y")
        os.makedirs(f"../dados/csv/{dia}", exist_ok=True)
        arquivo = f"../dados/csv/{dia}/{ticker}_stock_data.csv"

        df_stock = pd.DataFrame([{
            'Data_minute': data_minute,
            'Valor': price,
            'Ticker': ticker
        }])

        if os.path.exists(arquivo):
            df_stock.to_csv(arquivo, mode='a', index=False, header=False)
        else:
            df_stock.to_csv(arquivo, index=False)
        logging.info(f"Dados salvos para {ticker}: {price}")
    except Exception as e:
        logging.error(f"Erro ao salvar dados para {ticker}: {e}")

def extract_price(ticker, url, intervalo):
    """
    Extrai o preço do ativo utilizando o navegador Selenium.

    Args:
        ticker (str): Nome do ativo.
        url (str): URL do ativo no Google Finance.
    """
    try:
        if intervalo:
            logging.info(f"Extraindo dados para {ticker}...")
            driver.get(url)
            t.sleep(2)
            price_element = driver.find_element("xpath", '//*[@class="YMlKec fxKbKc"]')
            price = price_element.text
            save_data_to_csv(ticker, price)
            gerar_grafico_html("BTC-BRL", True)
        else:
            logging.info(f"Fora do horário de funcionamento para {ticker}.")
    except Exception as e:
        logging.error(f"Erro ao extrair dados para {ticker}: {e}")

def intervalo_acoes():
    now = datetime.now()
    return now.weekday() < 5 and time(10, 0) <= now.time() <= time(18, 0)

def intervalo_btc():
    now = datetime.now()
    return now.weekday() < 7

def extract_btc():
    extract_price("BTC-BRL", "https://www.google.com/finance/quote/BTC-BRL", intervalo_btc())

def extract_petr4():
    extract_price("PETR4", "https://www.google.com/finance/quote/PETR4:BVMF", intervalo_acoes())

def extract_nvdc34():
    extract_price("NVDC34", "https://www.google.com/finance/quote/NVDC34:BVMF", intervalo_acoes())

def extract_mxrf11():
    extract_price("MXRF11", "https://www.google.com/finance/quote/MXRF11:BVMF", intervalo_acoes())

def extract_appl34():
    extract_price("APPL34", "https://www.google.com/finance/quote/AAPL34:BVMF", intervalo_acoes())

def main():
    # Inicia o navegador
    start_browser()
    while True:
        extract_btc()
        extract_petr4()
        extract_nvdc34()
        extract_mxrf11()
        extract_appl34()
        t.sleep(60)
    stop_browser()

if __name__ == "__main__":
    main()
