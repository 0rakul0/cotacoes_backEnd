# Cotações — FastAPI, carteira e análise financeira

Aplicação pessoal para acompanhar ativos da B3, FIIs, BDRs, criptoativos e ações internacionais. A API é construída em **FastAPI**, utiliza **SQLite** e oferece histórico de preços, carteira, operações, proventos, risco e indicadores financeiros. O frontend estático HTML/CSS/JavaScript agora está **incorporado em `frontend/`** deste repositório; o projeto original [cotacoes_frontend_react](https://github.com/0rakul0/cotacoes_frontend_react) é mantido somente como origem histórica até verificação do backup.

**Branch principal deste repositório: `master`.** O repositório ainda não possui uma branch chamada `main`. Mudanças foram aplicadas à branch principal existente, sem criação de novas branches.

## Visão da arquitetura

| Camada | Arquivos | Responsabilidade |
|---|---|---|
| API | `main.py` | FastAPI, validação, segurança opcional, documentação OpenAPI |
| Preços | `cotacoes/market.py`, `cotacoes/service.py` | Consultas yfinance e cache |
| Armazenamento | `cotacoes/storage.py` | SQLite, posições manuais e histórico |
| Livro de operações | `cotacoes/ledger.py` | Compras, vendas, custo médio, ganhos realizados e rendimentos informados |
| Estatística | `cotacoes/analysis.py` | Volatilidade, drawdown, VaR, CVaR, correlações e eventos de retorno |
| Fundamentos | `cotacoes/fundamentals.py` | Indicadores Yahoo Finance e eventos de dividendos |
| Histórico legado | `cotacoes/import_legacy.py` | Migração dos CSVs antigos de 2024 |

O projeto reúne ideias dos repositórios `analise_fundamental`, `cotacaopython`, `cienciaDeDados` e `TimesSeriesAgent` sem importar diretamente seus scrapers antigos nem instalar PyTorch no servidor principal. O último permanece como pipeline de pesquisa **independente**: as análises estatísticas leves foram recriadas nesta API, mas **não** existe integração de inferência LSTM/Transformer ou busca de notícias em produção.

## Instalação

Python **3.10 ou superior**.

Linux:

    git clone https://github.com/0rakul0/cotacoes_backEnd.git
    cd cotacoes_backEnd
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    python -m uvicorn main:app --host 127.0.0.1 --port 7777

Windows PowerShell:

    git clone https://github.com/0rakul0/cotacoes_backEnd.git
    cd cotacoes_backEnd
    py -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    python -m uvicorn main:app --host 127.0.0.1 --port 7777

O painel web está incluído em `frontend/`, sem necessidade de clonar outro repositório ou instalar Node.js. Opcionalmente, use `COTACOES_FRONTEND_DIR` para servir uma versão alternativa dos arquivos.

- Painel: http://127.0.0.1:7777
- Swagger: http://127.0.0.1:7777/docs
- Saúde: http://127.0.0.1:7777/api/health

No primeiro startup, o SQLite é inicializado em `data/cotacoes.sqlite3`, salvo configuração em contrário. **Não publique o SQLite no Git.**

## API de ativos

| Método | Endpoint | Ação |
|---|---|---|
| GET | `/api/health` | Saúde |
| GET / POST | `/api/assets` | Listar / adicionar tickers |
| DELETE | `/api/assets/{symbol}` | Remover da lista de acompanhamento |
| POST | `/api/assets/{symbol}/refresh?force=true` | Consultar histórico diário via Yahoo Finance |
| GET | `/api/assets/{symbol}/history?period=6mo` | Consultar preços armazenados |
| GET | `/api/assets/{symbol}/fundamentals` | Snapshot fundamentalista em cache |
| POST | `/api/assets/{symbol}/fundamentals/refresh` | Atualizar os indicadores |
| GET | `/api/assets/{symbol}/dividends?days=365` | Dividendos **por unidade**, associados à ex-data |
| POST | `/api/assets/{symbol}/dividends/refresh` | Atualizar dados de dividendos do mercado |

Os períodos de histórico são `1mo`, `3mo`, `6mo`, `1y`, `5y` e `max`. A atualização dos preços é **sob demanda** e limitada por cache: não é um feed minuto a minuto. O cache padrão usa 30 minutos para preços e 24 horas para indicadores e dividendos; o parâmetro `force=true` ignora o cache.

### Indicadores disponíveis conforme o provedor

P/L, P/VP, VPA, LPA, ROE, margens, dividend yield, dívida/patrimônio, valor de mercado, volume e setor. Campos não fornecidos pelo Yahoo Finance são retornados como `null`, não estimados.

Dividendos de mercado e `/api/portfolio/incomes` são coisas diferentes: o primeiro registra **eventos por unidade**, o segundo são **recebimentos manuais da carteira**. Eventos podem estar incompletos e não são comprovantes de pagamento.

## Carteira e operações

| Método | Endpoint | Ação |
|---|---|---|
| GET | `/api/portfolio` | Posições e totais por moeda |
| PUT | `/api/portfolio/positions` | Cadastro legado de quantidade e preço médio |
| DELETE | `/api/portfolio/positions/{symbol}` | Remove posição manual |
| GET / POST | `/api/portfolio/trades` | Lista / registra compras e vendas |
| DELETE | `/api/portfolio/trades/{id}` | Exclui uma operação se a carteira continuar válida |
| GET / POST | `/api/portfolio/incomes` | Lista / registra rendimentos efetivamente recebidos |
| DELETE | `/api/portfolio/incomes/{id}` | Exclui um rendimento |

Registrar compra:

    curl -X POST http://127.0.0.1:7777/api/portfolio/trades -H "Content-Type: application/json" -d '{"symbol":"PETR4","side":"BUY","quantity":"10","unit_price":"35.20","fee":"2.00","currency":"BRL","traded_at":"2026-01-07T12:00:00-03:00"}'

Registrar venda: `side: "SELL"`. A API impede vendas superiores ao saldo disponível na **data da operação**, inclusive ao inserir operações antigas. O preço médio de compra inclui taxas e o resultado de vendas desconta a taxa da venda. Operações de um ticker devem estar na mesma moeda. As posições manuais continuam existindo para compatibilidade, mas se um ticker possuir operações, **o livro de operações prevalece**.

Registrar rendimento:

    curl -X POST http://127.0.0.1:7777/api/portfolio/incomes -H "Content-Type: application/json" -d '{"symbol":"MXRF11","kind":"DIVIDEND","amount":"25.00","withholding":"0.00","currency":"BRL","received_at":"2026-03-10T00:00:00-03:00"}'

Tipos permitidos: `DIVIDEND`, `JCP`, `RENTAL`, `OTHER`. O resultado da carteira separa **ganho não realizado**, **ganho realizado** e **rendimento líquido recebido**. Não calcula automaticamente impostos, eventos corporativos, desdobramentos ou lucro fiscal.

## Análise histórica

| Método | Endpoint | Ação |
|---|---|---|
| GET | `/api/analysis/risk/PETR4?days=365&confidence=0.95` | Volatilidade, drawdown, VaR e CVaR |
| GET | `/api/analysis/events/PETR4?days=365&threshold_pct=2` | Dias com oscilação acima do limiar |
| GET | `/api/analysis/correlation?symbols=PETR4,VALE3&days=365` | Correlação de Pearson dos retornos diários e janela móvel |
| GET | `/api/analysis/allocation` | Concentração por ticker, setor e moeda (sem conversão implícita) |
| GET | `/api/analysis/portfolio-risk?days=365` | Risco histórico **hipotético** com pesos atuais constantes |

Regras:
- O histórico usado na análise estatística contém **um fechamento por dia**. Se houver CSV intradiário e fechamento diário no mesmo dia, prevalece o dado do provedor diário.
- Retornos são calculados por `preço_atual / preço_anterior - 1`; lacunas superiores a 10 dias são desconsideradas.
- Para risco e correlação são necessários no mínimo **30 retornos diários** válidos.
- Volatilidade anualizada usa 252 sessões para ações/FIIs e 365 para BTC/ETH/SOL.
- VaR e CVaR são **estimativas históricas da pior cauda discreta**. Não garantem limites de perda.
- Correlação só é calculada para pares com mesma moeda e datas de retornos compartilhadas.
- A concentração mostra pesos por ticker, setor e classe, além do índice HHI e número efetivo de ativos por moeda; classificações ausentes são explicitadas.
- Risco da carteira usa os pesos **atuais** e rebalanceamento hipotético: não reconstrói a carteira histórica.
- Preços não incluem taxas, impostos, câmbio, dividendos ou inflação; para retorno total de longo prazo ainda falta um motor de eventos corporativos.

### Exemplo: risco de um ticker

    curl "http://127.0.0.1:7777/api/analysis/risk/PETR4?days=365&confidence=0.95"

O histórico pode estar vazio após o cadastro de um ativo. É necessário atualizar o ticker antes das análises.

## Importação dos CSVs antigos

Os arquivos legados continuam disponíveis em `dados/csv/`. Para importar sem apagar os originais:

    python -m cotacoes.import_legacy

Use `--dir CAMINHO` para outra pasta. A importação é repetível por ticker e instante. Arquivos legados com horário intradiário **não especificam fuso** e devem ser tratados com essa limitação.

## Configuração, serviço e segurança

Variáveis opcionais:

| Variável | Padrão | Finalidade |
|---|---|---|
| `COTACOES_DB_PATH` | `data/cotacoes.sqlite3` | Banco local |
| `COTACOES_FRONTEND_DIR` | `frontend/` | Diretório web estático |
| `COTACOES_CACHE_MINUTES` | `30` | Cache de preços |
| `COTACOES_FUNDAMENTALS_TTL_HOURS` | `24` | Cache de indicadores |
| `COTACOES_DIVIDENDS_TTL_HOURS` | `24` | Cache de dividendos |
| `COTACOES_API_TOKEN` | vazio | Habilita autenticação por header `X-API-Key` em `/api/*` salvo `/api/health` |

`COTACOES_API_TOKEN` é opcional para uso local, mas **obrigatório antes de disponibilizar os dados por rede**, junto com HTTPS/reverse proxy e controles adicionais adequados. O frontend atual não possui campo para fornecer a chave: com token configurado, clientes da API devem enviar o header.

Em Linux há um exemplo de serviço em `deploy/cotacoes.service.example` para rodar com systemd. Ajuste usuário, diretório, host e variáveis antes de instalar.

## Atualizacao automatica opcional

O monitoramento antigo utilizava Selenium e gerava arquivos HTML pesados. Foi substituido por uma rotina sem navegador:

    python -m monitoramento.monitorar --once

Para executar a cada hora no mesmo processo:

    python -m monitoramento.monitorar --loop --interval-minutes 60

Na instalacao Linux, prefira o **systemd timer** de `deploy/cotacoes-refresh.timer.example` e o servico `deploy/cotacoes-refresh.service.example`. Eles fazem atualizacao periodica em processo separado da API. O arquivo `deploy/cotacoes.service.example` serve para manter o FastAPI online.

Os preços sao historicos diarios; chamar o coletor de hora em hora **nao** transforma o provedor em fonte de precos ao vivo. O modo `--force` pode ignorar o cache, mas deve ser usado com parcimonia.

## Testes

    pip install -r requirements-dev.txt
    pytest -q

Os testes usam SQLite temporário e mocks; não requisitam dados reais em rede. Há também um workflow de CI para pushes na `master`.

## Próximas extensões

1. Reconstrução de posições históricas para rentabilidade ponderada no tempo ou pelo dinheiro.
2. Dividendos reais, splits, bonificações, tributação, eventos corporativos e benchmarks (CDI/Ibovespa).
3. Reconciliação/importação de notas de corretagem e extratos.
4. Adaptação do `TimesSeriesAgent` como serviço independente, com endpoint JSON versionado, validação fora da amostra e isolamento de dependências pesadas.
5. Painel web de operações, FIIs, risco e alertas, usando os endpoints novos.

> Projeto pessoal de estudo e acompanhamento. Não constitui orientação de compra ou venda. Fontes de mercado podem falhar, sofrer atraso ou retornar dados incompletos.

## Preservação dos projetos financeiros antigos

A migração foi organizada em `migration/README.md`, com commits fixos de origem, snapshots de código/dados em `legacy_sources/` e um script de backup local do histórico Git (não publicado automaticamente). Não apague os repositórios antigos sem validar todos os backups e o `legacy_sources/manifest.json`.
