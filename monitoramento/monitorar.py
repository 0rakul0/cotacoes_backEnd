"""
python monitorar.py "AAPL34:BVMF", "NVDC34:BVMF", "AAPL34:BVMF", "AMZO34:BVMF", "MXRF11:BVMF", "PETR4:BVMF"
"""

import time
import threading
from cotacoes_btc import Cotacoes_BTC
from cotacoes_mxrf import Cotacoes_MXRF
from cotacoes_petr4 import Cotacoes_PETR4
from cotacoes_nvida import Cotacoes_NVDC34
from cotacoes_appl34 import Cotacoes_APPL

class MonitorThread(threading.Thread):
    def __init__(self, monitor, stop_event):
        """
        Thread para monitorar um ativo específico.

        :param monitor: Objeto do monitor (ex: Cotacoes_BTC)
        :param stop_event: Evento que sinaliza para parar a execução.
        """
        super().__init__()
        self.monitor = monitor
        self.stop_event = stop_event

    def run(self):
        """
        Método principal da thread.
        """
        while not self.stop_event.is_set():
            self.monitor.run()
            time.sleep(60)  # Intervalo fixo de 60 segundos

def main():
    # Cria os monitores
    monitores = [
        Cotacoes_MXRF(),
        Cotacoes_BTC(),
        Cotacoes_PETR4(),
        Cotacoes_NVDC34(),
        Cotacoes_APPL()
    ]

    # Evento para parar todas as threads
    stop_event = threading.Event()

    # Cria as threads para cada monitor
    threads = [MonitorThread(monitor, stop_event) for monitor in monitores]

    try:
        # Inicia todas as threads
        for thread in threads:
            thread.start()

        print("Monitores iniciados. Pressione Ctrl+C para parar.")

        # Mantém o programa principal em execução até que seja interrompido
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nEncerrando monitores...")
        stop_event.set()  # Sinaliza para todas as threads pararem

        # Aguarda todas as threads finalizarem
        for thread in threads:
            thread.join()

        print("Todos os monitores foram encerrados com sucesso.")

if __name__ == "__main__":
    main()
