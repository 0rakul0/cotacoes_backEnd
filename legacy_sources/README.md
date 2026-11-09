# Fontes antigas preservadas para migração

Esta pasta é gerada automaticamente por scripts/migrate_legacy.py, com conteúdo selecionado de projetos financeiros antigos de 0rakul0.

**NÃO execute e NÃO importe estes scripts na API.** Eles ficam aqui como referência histórica. O backend funcional permanece em cotacoes/.

- manifest.json identifica cada origem, commit, arquivo, tamanho e SHA256, e também o que foi excluído.
- Os arquivos desta pasta são snapshots, **não** cópias completas do histórico Git.
- Para preservar todos os commits, use scripts/backup_legacy.sh em um local privado.
- Não apagar repositórios antigos antes da verificação e do backup.
- Não publicar arquivos de carteira pessoal, tokens ou configurações sensíveis.
- Pesos de modelos PyTorch arquivados são dados e não devem ser carregados automaticamente.

Documentação: migration/README.md.
