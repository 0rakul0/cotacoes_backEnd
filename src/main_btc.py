import time
import pandas as pd
from datetime import datetime, time as dt_time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from matplotlib import pyplot as plt
import numpy as np
import os
from plyer import notification
import concurrent.futures

class cotacoes():
    def run(self, ticker):
        # Inicialização do navegador (visível)
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        driver = webdriver.Chrome(options=chrome_options)


        driver.get(f"https://www.google.com/finance/quote/{ticker}")

        try:
            print(f"Iniciando o monitoramento... ticker {ticker}")
            while True:
                if self.is_market_open():
                    dia = datetime.today().strftime("%d-%m-%Y")
                    os.makedirs(f"../dados/csv/{dia}", exist_ok=True)
                    self.STOCK_CSV_PATH = f"../dados/csv/{dia}/stock_data"
                    data_minute = datetime.now().strftime("%Y-%m-%d %H:%M")
                    self.start(ticker, driver, data_minute)
                    self.graph_price(ticker)
                else:
                    print("Fora do horário de mercado. Aguardando para retomar...")
                time.sleep(60)

        except KeyboardInterrupt:
            print(f"Encerrando o monitoramento... ticker {ticker}")

        finally:
            c.close_browser(driver)
            print("Navegador fechado.")

    def start(self, ticker, driver, data_minute):
        try:
            price_element = driver.find_element("xpath", '//*[@class="YMlKec fxKbKc"]')
            price = price_element.text

            arquivo = f'{self.STOCK_CSV_PATH}_{str(ticker).split(':')[0]}.csv'
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

    def notifica(self,media, maxima, minima, atual, ticker):
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

    def graph_price(self,ticker):
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

            # Configura o gráfico
            plt.figure(figsize=(10, 6))
            plt.plot(df.index, df["Valor"], label=ticker)
            plt.title(f"Variação dos Preços de {ticker}")
            plt.xlabel("Data e Hora")
            plt.ylabel("Preço Médio (R$)")
            plt.legend()
            plt.xticks(rotation=45)

            # Adiciona linhas verticais a cada 30 minutos
            for i in range(0, len(df.index), 120):  # Assumindo dados a cada 5 minutos, 6*5min = 30min
                plt.axvline(df.index[i], color='gray', linestyle='--', linewidth=0.5)

            for i in range(0, len(df.index), 240):  # Assumindo dados a cada 5 minutos, 12*5min = 60min
                plt.axvline(df.index[i], color='black', linestyle='--', linewidth=0.6)

            ultimo_valor = df["Valor"].iloc[-1]
            ultima_data = df.index[-1]
            plt.text(ultima_data, ultimo_valor, f"{ultimo_valor:.2f}", color='red', fontsize=10,
                     verticalalignment='bottom')

            x = np.arange(len(df.index))
            y = df["Valor"].values
            if len(x) > 1:
                coef = np.polyfit(x, y, 1)  # Ajuste linear
                tendencia = np.poly1d(coef)  # Gera função de tendência

                # Determina o rótulo com base na inclinação da linha de tendência
                rotulo_tendencia = "Subindo" if coef[0] > 0 else "Queda"

                # Plota a linha de tendência com o rótulo adequado
                plt.plot(df.index, tendencia(x), color="orange", linestyle="--",
                         label=f"Tendência ({rotulo_tendencia})")
                plt.legend()

            maxima = df["Valor"].max()
            minima = df["Valor"].min()
            media = df["Valor"].mean()

            if maxima == ultimo_valor or minima == ultimo_valor:
                self.notifica(media, maxima, minima, ultimo_valor, ticker)

            # Adiciona linhas horizontais para a máxima e mínima histórica
            plt.axhline(maxima, color="green", linestyle="--", label=f"Máxima: {maxima:.2f}")
            plt.axhline(minima, color="red", linestyle="--", label=f"Mínima: {minima:.2f}")

            # Adiciona os valores de máxima e mínima em caixas (quadradinhos)
            plt.text(df.index[int(len(df.index) * 0.05)], maxima, f'Máxima: {maxima:.2f}', color="green", fontsize=10,
                     bbox=dict(facecolor='white', edgecolor='green', boxstyle='round,pad=0.5'))
            plt.text(df.index[int(len(df.index) * 0.05)], minima, f'Mínima: {minima:.2f}', color="red", fontsize=10,
                     bbox=dict(facecolor='white', edgecolor='red', boxstyle='round,pad=0.5'))

            plt.tight_layout()

            # Salva o gráfico na pasta img
            img_path = os.path.join(img_folder, f"{str(ticker).split(':')[0]}.png")
            plt.savefig(img_path)
            plt.close()


    def is_market_open(self):
        """Verifica se o mercado está aberto (segunda a sexta, entre 10:00 e 18:20)."""
        now = datetime.now()
        return now.weekday() < 7 #and dt_time(10, 0) <= now.time() <= dt_time(18, 20)


    def close_browser(self, driver):
        """Fecha o navegador ao final do script."""
        driver.quit()



if __name__ == "__main__":
    # Configuração dos tickers e caminhos dos CSVs "NVDC34:BVMF", "AAPL34:BVMF", "AMZO34:BVMF", "MXRF11:BVMF", "PETR4:BVMF",
    TICKERS = ["BTC-BRL"]

    c = cotacoes()

    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {executor.submit(c.run, ticker): ticker for ticker in TICKERS}
        for future in concurrent.futures.as_completed(futures):
            ticker = futures[future]
            try:
                future.result()
            except Exception as e:
                print(f"Erro ao processar o ticker {ticker}: {e}")


