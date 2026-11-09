#!/usr/bin/env bash
set -euo pipefail

# Backup COMPLETO de cada repositorio incluindo todo o historico Git.
# Execute SOMENTE em ambiente local e armazene em local privado e seguro.
# Uso: bash scripts/backup_legacy.sh /caminho/externo/seguro

if [[ "$#" -ne 1 ]]; then
  echo "Uso: bash scripts/backup_legacy.sh DIRETORIO_EXTERNO_SEGURO" >&2
  exit 2
fi
mkdir -p "$1"
OUT="$(cd "$1" && pwd)"
case "$OUT" in
  "$PWD"|"$PWD/"*)
    echo "ERRO: escolha diretorio fora do repositorio principal." >&2
    exit 2
  ;;
esac

while IFS=$'\t' read -r repository branch pinned; do
  if [[ -z "$repository" ]]; then
    continue
  fi
  echo "Criando bundle privado de 0rakul0/$repository ($branch @ $pinned)"
  bare="$OUT/$repository.git"
  if [[ -e "$bare" ]]; then
    echo "ERRO: diretorio de backup ja existe; escolha diretorio novo: $bare" >&2
    exit 1
  fi
  git clone --quiet --mirror "https://github.com/0rakul0/$repository.git" "$bare"
  actual="$(git -C "$bare" rev-parse "refs/heads/$branch")"
  if [[ "$actual" != "$pinned" ]]; then
    echo "ERRO: origem mudou em $repository. Revise o SHA antes de continuar." >&2
    exit 1
  fi
  bundle="$OUT/$repository.bundle"
  git -C "$bare" bundle create "$bundle" --all
  git -C "$bare" bundle verify "$bundle"
  rm -rf "$bare"
done < <(python -c 'import json,pathlib; p=pathlib.Path("migration/sources.json"); print("\n".join("\t".join((x["repository"],x["branch"],x["sha"])) for x in json.loads(p.read_text())))')
(
  cd "$OUT"
  sha256sum ./*.bundle > SHA256SUMS.txt
)
echo "Bundles completos e hashes armazenados PRIVADAMENTE em $OUT"
echo "Nao publique estes bundles em releases publicas: historicos antigos podem conter segredos."
