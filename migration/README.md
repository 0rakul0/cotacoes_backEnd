# Migração dos projetos financeiros para cotações

## Regra de segurança

O repositório central continua sendo **0rakul0/cotacoes_backEnd**, branch principal **master**. Esta migração NÃO apaga, arquiva no GitHub nem desativa os repositórios de origem automaticamente.

**Não excluir nenhum repositório original até:**
1. Confirmar que a execução da workflow de migração ficou verde.
2. Confirmar que a pasta legacy_sources e seu manifest.json foram enviados para master.
3. Executar **localmente**, fora da pasta do repositório, `bash scripts/backup_legacy.sh /caminho/privado`, gerando os 7 bundles Git e SHA256SUMS.txt. Não publicar estes bundles em repositórios ou releases públicos.
4. Testar a restauração de um bundle, por exemplo: `git clone TimesSeriesAgent.bundle restored-TimesSeriesAgent`.
5. Decidir quais arquivos excluídos do snapshot também devem ser preservados fora do Git. O relatório manifest.json contém a lista completa de exclusões por origem.
6. Conferir que rotinas, datasets e resultados necessários foram de fato adaptados e validados antes de fechar o projeto antigo.

A presença de arquivos em legacy_sources significa **cópia arquivada**, não integração em produção nem preservação de todo o histórico. Os bundles privados são necessários para preservar o histórico completo. **Esta operação não é executada automaticamente pelo CI**, para não publicar inadvertidamente segredos ou dados pessoais que possam existir nas versões antigas.

## Repositórios fonte

| Projeto | Conteúdo selecionado | Estado de migração |
| --- | --- | --- |
| TimesSeriesAgent | src, eval, train, modelos incluindo .pt, dados e resultados CSV, notebooks/textos de pesquisa | Snapshot arquivado; modelos e notícias NÃO integrados à API |
| cotacaopython | coletores, calculadora, simulações, CSVs e notebooks de FIIs | Snapshot arquivado; scraping legado NÃO executado |
| analise_fundamental | scripts, notebooks e utilitários | Snapshot arquivado; indicadores novos já têm módulo separado no FastAPI |
| Projeto_ciencia_de_dados_acoes | carteira_de_acoes.ipynb, balanços .xls, Cotacoes.xlsx e LICENSE | Dados brutos históricos arquivados, não validados como indicadores atuais |
| cienciaDeDados | scripts de finanças, risco, estatística e README | Conceitos de risco já reimplementados com testes; scripts preservados |
| notificacao_com_python | rascunho de alertas e README | Snapshot preservado, disparo de mensagens NÃO integrado |
| cotacoes_frontend_react | HTML, CSS e JS sem React | Cópia ativa no diretório frontend/ do próprio backend e snapshot de origem |

Outras partes dos repositórios (executáveis, caches, dashboards HTML gerados, dados de outras disciplinas e arquivos sensíveis como "minha_carteira") **não entram** no snapshot selecionado. Estão no backup Git completo, caso seja publicado com sucesso.

## Organização

- migration/sources.json: repositório, branch e **SHA de commit fixo** de cada origem.
- scripts/migrate_legacy.py: download do commit fixo e cópia dos arquivos permitidos, sem executar scripts antigos.
- legacy_sources/{nome}/...: arquivos originais com estrutura preservada.
- legacy_sources/manifest.json: SHA256 e tamanho de cada arquivo copiado, mais lista explícita dos que ficaram de fora.
- scripts/backup_legacy.sh: gera bundles Git com todas as refs e todo o histórico **somente em pasta privada escolhida pelo operador**.
- .github/workflows/migrate-legacy.yml: executa o processo em GitHub Actions e publica o snapshot diretamente na master.

**Atenção:** não importamos código diretamente de legacy_sources em main.py. O código legado pode depender de serviços descontinuados ou bibliotecas antigas. Use-o apenas como fonte para desenvolver módulos novos, com revisão e testes.

## Atualização futura

Se algum repositório de origem receber mudanças, atualize seu SHA de forma explícita em migration/sources.json e revise o diff antes de reexecutar. A workflow será acionada no push da master; nenhuma branch adicional é necessária.

## Restauração de histórico antigo (bundle)

Execute o script de backup local, confira o SHA256 do bundle em SHA256SUMS.txt e então, na pasta privada de backup:

    git clone TimesSeriesAgent.bundle TimesSeriesAgent-restaurado

Para os dados selecionados já em master, confira:

    python scripts/migrate_legacy.py --verify-only

**Nota sobre tamanho**: pesos .pt, planilhas .xls/.xlsx e logs CSV são arquivos de preservação e não devem ser carregados automaticamente no processo web. O frontend e a API continuam leves.
