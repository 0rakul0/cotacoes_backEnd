# Modelos por ativo: desenho, governança e treinamento

Cada ticker cadastrado possui um **registro independente**. O fluxo separa três tarefas:

1. O coletor atualiza o SQLite com fechamentos diários.
2. Um worker offline executa treino/avaliação e salva pesos versionados por ticker.
3. O FastAPI **só lê** metadados e executa inferência de modelo selecionado, quando disponível.

Nenhum treinamento ocorre durante um GET, ao abrir o dashboard ou ao registrar o ativo.

## Etapas de treinamento

O worker lê um segmento com pelo menos 260 dias de fechamento, sem atravessar lacunas de mais de 10 dias. Calcula o retorno logarítmico diário, cria janelas de 20 retornos e usa **o próximo retorno** como alvo (um passo à frente).

Os dados são divididos cronologicamente:
- 70% para aprendizado dos parâmetros e cálculo das estatísticas de normalização;
- 15% para escolher hiperparâmetros e arquitetura;
- 15% para teste, sem participar da seleção.

O baseline é manter o último fechamento (retorno logarítmico zero). Uma arquitetura só é selecionada se superar a métrica RMSE de validação desse baseline em pelo menos 1%. **O teste isolado é um diagnóstico, não uma garantia de capacidade preditiva.**

São registradas versões no SQLite e arquivos em data/model_artifacts/{ticker}/{modelo}/{versao}.json (.pt se neural). A verificação de hashes protege contra alterações acidentais. O histórico de preços é identificado por um fingerprint que inclui a janela de features. Versionamento por ticker evita que parâmetros ou normalizadores de uma série sejam reutilizados em outra.

## Arquiteturas disponíveis

| Família | Dependências | Observação |
|---|---|---|
| ridge | numpy, dependência base | Modelo linear regularizado para medir sinal temporal |
| lstm | PyTorch opcional | Modelo recorrente de retornos |
| autoencoder | PyTorch opcional | Encoder de retornos, reconstrução auxiliar e previsão |
| transformer | PyTorch opcional | Encoder com embeddings posicionais de janelas de retornos |

As classes derivam conceitualmente do TimesSeriesAgent antigo, mas **não carregam os pesos .pt legados**, pois treinamento, parâmetros e colunas antigas não coincidem com a representação atual.

## Comandos

Atualize a série primeiro:

    python -m monitoramento.monitorar --once

Treine o baseline para todos os ativos:

    python -m cotacoes.model_jobs train --all --family ridge

Treine as arquiteturas para PETR4 usando ambiente com PyTorch:

    pip install -r requirements-ml.txt
    python -m cotacoes.model_jobs train --symbol PETR4 --family all --epochs 60

Veja as versões selecionadas:

    python -m cotacoes.model_jobs status

Ou consulte a API:

    GET /api/models
    GET /api/models/PETR4
    GET /api/models/PETR4/forecast

Se não houver dados suficientes, os ativos permanecem como not_trained; se os modelos não melhorarem o baseline, permanecem apenas como candidatos. Um modelo validado pode perder qualidade com o tempo. Cabe monitorar degradação e retreinar.

## Agendamento

Existem exemplos em deploy/cotacoes-models.service.example e deploy/cotacoes-models.timer.example. O timer executa somente o baseline leve uma vez por semana; treinar LSTM/Autoencoder/Transformer exige dependências opcionais, maior tempo e recursos. Não é instalado automaticamente.

## Limitações importantes

- O modelo usa somente preços de fechamento, **sem notícias, Brent, CDI, câmbio, splits, dividendos ou fundamentos**. O motor de notícias do TimesSeriesAgent continua arquivado e precisará de adaptação posterior.
- Modelos treinados com preços não ajustados podem sofrer distorções por eventos corporativos. É necessário migrar para séries ajustadas/total return antes de afirmar rentabilidade econômica.
- A validação temporal usa um holdout simples; antes de uso sério, implementar walk-forward periódico, checagem de mudanças de regime, sensibilidade de hiperparâmetros e intervalos de incerteza calibrados.
- A API exibe previsão experimental D+1, não sinal de compra/venda. Exige atualização recente de cotação (até 14 dias).
- Indicadores mostram o erro do modelo em pontos percentuais de retorno diário, não o erro relativo do preço.
- O diretório data/model_artifacts é persistente, fica fora do Git e requer backup seguro. O SQLite guarda registro e metadados, mas não substitui os arquivos de pesos.
