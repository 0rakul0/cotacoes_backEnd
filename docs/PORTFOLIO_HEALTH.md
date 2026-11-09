# Saúde dos fundos - investigação documental

O principal objetivo deste módulo é analisar os riscos presentes **dentro** de um ativo financeiro (FII ou FIAGRO), com evidências oficiais rastreáveis. As partes da carteira podem ser: CRI, CRA, FII/FIAGRO investido, permuta, imóvel e instrumentos de crédito diversos.

**Atenção à diferença entre os riscos:** vacância se refere a imóveis para locação; CRIs/CRAs envolvem risco de crédito, lastro e garantia; permutas envolvem obras, vendas, distratos e repasses. Unidades ainda não vendidas NÃO equivalem a vacância locatícia.

## Fontes

Prioridade de pesquisa:
1. B3/FundosNet, informes mensais, fatos relevantes, relatórios gerenciais e avisos de rendimentos.
2. Gestoras e administradores (como XP Asset e BTG Pactual).
3. Termos, escrituras e relatórios de securitizadoras CRI/CRA.
4. Informes específicos dos FIIs investidos e documentos regulatórios CVM.

Agregadores servem para **localizar** documentos, mas a confirmação de eventos e datas deve ser feita nas fontes oficiais.

## Piloto MXRF11

Relatório oficial de setembro de 2026 (publicado 03/11/2026):
https://fnet.bmfbovespa.com.br/fnet/publico/exibirDocumento?id=1367646

Aviso oficial de 30/10/2026:
https://fnet.bmfbovespa.com.br/fnet/publico/exibirDocumento?cvm=true&id=1365016

O exemplo revisado manualmente inclui 23 posições, cinco ocorrências e duas datas certas de rendimento do fundo:
- Distribuição da carteira em set/26: 75% CRIs, 13,4% FIIs, 5,9% permutas e 5,7% caixa.
- CRIs: Urbplan integralmente provisionado, AIZ/Pesa em carência negociada e Arquiplan/Beside em recuperação judicial/execução de garantia.
- Permutas: dados de vendas, construção e entrega prevista, incluindo Brooklin 2/3/4, Morumbi 1, Campo Belo 3, Jardim Europa 2 e Vila Nova Conceição 2.
- FIIs: exemplos GARE11, LPLP11, XPHR Sub e OPI FII, que exigem análise de segunda camada.
- Próximo rendimento divulgado: R$ 0,095/cota, data-com 30/10/2026 e pagamento 16/11/2026.

**COBERTURA PARCIAL:** 23 posições não são a carteira integral do MXRF11. Sem documento, sem histórico ou sem informação de um CRI não significa risco baixo. A situação reflete a data-base do relatório; não é monitoramento em tempo real.

## Modelo de dados e avaliação

Cada snapshot versionado contém data-base, publicação, URL primária, lista de posições, eventos, evidências e calendário. É gravado no SQLite com hash de conteúdo e identificação da origem.

O calendário só contém datas de pagamento explicitamente documentadas. "Mensal" não identifica o dia de cupom e vencimento AAAA-MM não identifica o dia do vencimento. Não usamos cálculo automático de vencimento no primeiro ou último dia do mês.

Regras de triagem:
- Recuperação judicial, provisão integral ou inadimplência confirmada: crítico.
- Reestruturações, carência negociada, execução de garantias: atenção.
- Permuta com obra acima de 75% e vendas abaixo de 40%: atenção a estoque.
- Entrega prevista antes da data-base e obra ainda não concluída: atenção ao cronograma.
- Imóvel locado com vacância divulgada acima de 20%: atenção.
- Locação com vencimento contratual em até 12 meses: monitoramento.

Esses níveis NÃO são estimativas estatísticas da probabilidade de inadimplência ou de vacância. Sinais observados exigem evidência, julgamento e revisão constante.

## CLI e coleta de documentos

Exemplo incluído no primeiro startup, salvo COTACOES_SEED_HEALTH_EXAMPLE=0. Importação manual do JSON revisado:

    python -m cotacoes.document_pipeline import --file examples/mxrf11_2026_09.json

Baixar PDF do FNET no ambiente local, sem expor URL arbitrária pela API:

    python -m cotacoes.document_pipeline fetch --symbol MXRF11 --url "https://fnet.bmfbovespa.com.br/fnet/publico/exibirDocumento?id=1367646"

Extração preliminar de páginas e códigos de títulos (não confirma fatos automaticamente):

    pip install -r requirements-documents.txt
    python -m cotacoes.document_pipeline extract --symbol MXRF11 --pdf /caminho/relatorio.pdf --url "https://fnet.bmfbovespa.com.br/fnet/publico/exibirDocumento?id=1367646" --reference-date 2026-09-30 --published-at 2026-11-03

O arquivo staging gerado contém páginas, tabelas candidatas extraídas, trechos candidatos, códigos e SHA-256. A contagem de CRIs e os totais financeiros devem ser reconciliados manualmente antes de marcar cobertura completa. A revisão de tabelas e garantias é obrigatória. Nenhum código legado é executado nem PDFs são enviados ao Git.

## Endpoints

- GET /api/funds/MXRF11/health: resumo e lista de riscos documentados.
- GET /api/funds/MXRF11/documents: fontes oficiais.
- GET /api/funds/MXRF11/holdings: ativos dentro do fundo, com filtros category e risk.
- GET /api/funds/MXRF11/holdings/21F0568504: ficha individual do CRI AIZ/Pesa.
- GET /api/funds/MXRF11/calendar: rendimentos confirmados, meses de vencimento e cupons ainda sem dia exato.

Não há treinamento de modelos nesta API de investigação. Os modelos preditivos de preço por ticker permanecem isolados do estudo de risco contratual.

## Evolução necessária para cobertura total

Para atingir a meta de analisar cada empreendimento/CRI/CRA, precisamos:
1. Reconciliar todas as linhas do relatório oficial com o total de posições, sem omissões ou duplicações.
2. Abrir documentos de cada securitizadora para cronogramas de juros/amortizações e confirmar pagamentos efetivos.
3. Acompanhar os documentos de FIIs e FIAGROs investidos (look-through) e agregar exposição por devedor/imóvel.
4. Construir série temporal de contratos, ocupação, inadimplência, garantias, obras, vendas e distratos.
5. Separar o risco observado de uma probabilidade estimada e criar alertas de inconsistência e ausência de documento.

O inventário piloto pode ser consultado imediatamente, mas não certifica que todos os riscos do MXRF11 foram identificados.
