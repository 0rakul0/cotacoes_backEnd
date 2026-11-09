# extração da pagina alvo
# https://www.fundsexplorer.com.br/funds <- é onde fica a lista de informações dos fundos imobiliarios
# a mecanica é https://www.fundsexplorer.com.br/funds/mxrf11 a ultima parte informa a ação
# então temos etapa 1 entrar no site
# etapa 2 entrar com o fundo imobiliario
"""
  <div class="col-md-3 col-xs-12">
      <div id="item-ATSA11" class="fund-card">
        <div class="bg-wrapper"></div>
          <a href="/funds/atsa11">
            <span class="symbol">ATSA11</span>
            <div class="name-wrapper">
              <span class="name">HEDGE ATRIUM SHOPPING SANTO ANDRE FDO INV IMOB</span>
            </div>
          </a>
          <span class="admin-title">Adm.</span>
          <span class="admin">
            Hedge Investments</span>
      </div>
    </div>
"""
import requests

site = requests.get('https://www.fundsexplorer.com.br/funds')
print(site.content)