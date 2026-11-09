# Cotações — FastAPI e dashboard web

Projeto de acompanhamento de ativos e preparação para análise de portfólio. Backend em FastAPI, frontend estático HTML/CSS/JS, persistência SQLite e cotações históricas via yfinance.

## Repositórios

- Backend: https://github.com/0rakul0/cotacoes_backEnd
- Frontend estático: https://github.com/0rakul0/cotacoes_frontend_react

O React foi substituído por arquivos estáticos. Para servir o painel na mesma origem, clone o repositório frontend em uma pasta chamada frontend dentro deste backend ou configure a variável COTACOES_FRONTEND_DIR.

## Executar (Python 3.10+)

Windows PowerShell:

    py -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    python -m uvicorn main:app --reload --port 7777

Linux:

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    python -m uvicorn main:app --host 127.0.0.1 --port 7777

Acesse http://127.0.0.1:7777 para o painel e http://127.0.0.1:7777/docs para documentação da API.

## Endpoints

| Método | URL | Uso |
| --- | --- | --- |
| GET | /api/health | Saúde da API |
| GET, POST | /api/assets | Listar/adicionar ativos |
| DELETE | /api/assets/{symbol} | Remover da lista |
| GET | /api/assets/{symbol}/history?period=6mo | Histórico 1mo, 3mo, 6mo, 1y, 5y, max |
| POST | /api/assets/{symbol}/refresh?force=true | Buscar preços no provedor |
| GET | /api/portfolio | Posições, custos e ganhos por moeda |
| PUT | /api/portfolio/positions | Incluir/substituir posição |
| DELETE | /api/portfolio/positions/{symbol} | Remover posição |

Exemplo de corpo de posição: {"symbol":"PETR4","quantity":15,"avg_cost":32.5,"currency":"BRL"}

## Histórico legado

O repositório mantém CSVs originais de 2024 em dados/csv. Para importar ao SQLite execute:

    python -m cotacoes.import_legacy

Para importar de outra pasta use --dir /caminho/dos/csv. A importação pode ser executada mais de uma vez; registros com o mesmo ticker e instante são atualizados. Os dados antigos não possuem fuso horário explícito.

## Cache, moedas e qualidade

- Banco local persistente: data/cotacoes.sqlite3 (configurável por COTACOES_DB_PATH).
- Cache de consulta: 30 minutos (COTACOES_CACHE_MINUTES). Use force=true para ignorar o TTL.
- A API não realiza scraping contínuo. A atualização ocorre sob demanda.
- Os preços do yfinance são fechamentos diários, não preços ao vivo.
- Se o provedor falhar, preços anteriores permanecem no banco e a chamada retorna erro.
- Moedas diferentes são consolidadas separadamente, sem conversão fictícia.
- Carteira é apenas uma posição agregada por ativo, com custo médio manual; não calcula proventos, impostos, taxas ou movimentações históricas.
- Não exponha o painel sem autenticação na Internet: no estágio atual qualquer cliente da API pode editar posições.

Testar offline (com mocks): pip install -r requirements-dev.txt && pytest -q

## Evolução sugerida

1. Livro de transações: compras, vendas, custos, dividendos e desdobramentos.
2. Retorno total e rentabilidade ajustada, benchmarks, CDI e IPCA.
3. Concentração, diversificação, volatilidade e drawdown.
4. Exposição cambial e comparação por classe de ativo.
5. Rotina agendada de atualização, autenticação e perfis.

Ferramenta de acompanhamento e estudo, sem recomendação de investimento.
