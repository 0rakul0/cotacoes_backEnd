# Cotações — frontend estático

Interface simplificada em **HTML, CSS e JavaScript puro**, sem React, npm ou etapa de compilação.

Este repositório substitui o protótipo Create React App original. O backend oficial é https://github.com/0rakul0/cotacoes_backEnd e contém a API FastAPI.

## Como usar

1. Clone o backend e instale suas dependências conforme o README dele.
2. Clone este repositório dentro do backend, com o nome frontend:

    git clone https://github.com/0rakul0/cotacoes_frontend_react.git frontend

3. Execute o backend: python -m uvicorn main:app --host 127.0.0.1 --port 7777
4. Abra http://127.0.0.1:7777

Se o frontend estiver em outra pasta, configure COTACOES_FRONTEND_DIR apontando para ela. O FastAPI serve index.html na rota / e style.css e app.js em /static/.

## Funcionalidades

- Lista de ativos acompanhados e última cotação armazenada.
- Adição e retirada de tickers.
- Histórico interativo em SVG com intervalos 1 mês, 3 meses, 6 meses, 1 ano, 5 anos e total.
- Atualização sob demanda via provedor externo.
- Cadastro de quantidade, custo médio e moeda por ativo.
- Valor estimado e resultado não realizado; resumos separados por moeda.
- Layout responsivo e sem dependências de JavaScript externas.

## Limitações

A API não fornece cotações em tempo real e não executa atualizações automaticamente. Posições são valores informados manualmente e não representam extrato de corretora. Não há autenticação; não exponha publicamente sem configurar controle de acesso.

## Desenvolvimento

Edite diretamente index.html, style.css e app.js. As chamadas usam rotas relativas da API para evitar configurações de CORS.
