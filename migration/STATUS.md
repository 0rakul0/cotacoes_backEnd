# Estado da consolidação financeira

Snapshot de origem preservado na branch principal master em 2026-11-09. Este documento é uma fotografia da migração inicial, não um certificado de que os projetos antigos já podem ser excluídos.

| Origem | Arquivos preservados | Status de integração |
| --- | ---: | --- |
| TimesSeriesAgent | 101 | Código, modelos e resultados arquivados; inferência online e notícias pendentes |
| cotacaopython | 319 | Histórico e códigos arquivados; extração antiga não roda em produção |
| analise_fundamental | 10 | Códigos preservados; indicadores novos são calculados no módulo fundamentals.py |
| Projeto_ciencia_de_dados_acoes | 85 | Balanços e planilhas preservados; qualidade de dados pendente |
| cienciaDeDados | 10 | Estudos arquivados; risco e correlação reimplementados em analysis.py |
| notificacao_com_python | 2 | Rascunho arquivado; serviço de notificações pendente |
| cotacoes_frontend_react | 4 | HTML/CSS/JS ativo em frontend/ e snapshot preservado |

**Total confirmado:** 531 arquivos, 58.092.507 bytes. Original preservado em legacy_sources/ com hashes SHA-256 no manifest.json. Arquivos fora do escopo listados em excluded no manifesto. O histórico Git completo dos repositórios originais **ainda não foi copiado automaticamente**: use scripts/backup_legacy.sh em local privado e verifique os bundles antes de excluir qualquer origem. Nenhum repositório antigo foi apagado.

## Critério de encerramento por origem

1. Conferir hash do snapshot com python scripts/migrate_legacy.py --verify-only e testes de regressão.
2. Revisar todos os arquivos excluídos que possam ter valor para preservação.
3. Gerar backup **privado** do histórico Git completo e testar restauração.
4. Adaptar, testar e ativar os módulos necessários em cotacoes/; o diretório legacy_sources/ não é executável.
5. Só então decidir manualmente entre arquivar ou remover o repositório original.

Veja migration/README.md para a documentação técnica.
