#!/usr/bin/env python3
"""Snapshot auditavel de projetos financeiros antigos (nao executa codigo legado).

Executar em ambiente com git + acesso aos repositorios publicos:
    python scripts/migrate_legacy.py
    python scripts/migrate_legacy.py --verify-only

O arquivo migration/sources.json fixa cada SHA de origem. Nao atualizar
as referencias automaticamente sem revisar o que mudou.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "migration" / "sources.json"
DEST = ROOT / "legacy_sources"
MANIFEST = DEST / "manifest.json"

# Seleciona materiais financeiros relevantes. Nao copia binarios executaveis,
# ambientes de desenvolvimento, caches ou dados pessoais da carteira.
EXACT = {
    "TimesSeriesAgent": {
        "README.md", "pyproject.toml", "uv.lock", ".env_template",
        ".python-version", ".gitignore",
    },
    "cotacaopython": {"README.md", "requirements.txt", "runtime.txt", "Procfile"},
    "analise_fundamental": {"README.md", ".gitattributes"},
    "Projeto_ciencia_de_dados_acoes": {"README.md", "LICENSE", "carteira_de_acoes.ipynb"},
    "cienciaDeDados": {"README.md"},
    "notificacao_com_python": {"README.md", "AlertPython.py"},
    "cotacoes_frontend_react": {"README.md", "index.html", "style.css", "app.js"},
}
SKIP_PARTS = {
    ".git", ".idea", ".venv", "__pycache__", ".ipynb_checkpoints",
    "node_modules", "chromedriver", "chromedriver105", "windows_v1.8.0",
}
SKIP_NAMES = {"minha_carteira.csv", "minha_carteira.xlsx"}
SKIP_EXTENSIONS = {".exe", ".dll", ".so", ".pyc", ".pyo", ".tmp", ".bak"}
MAX_PER_FILE = 80 * 1024 * 1024


def eligible(repo: str, relative: str) -> bool:
    """Lista explicita de arquivos a arquivar: seguro para inspecao, nao execucao."""
    path = PurePosixPath(relative)
    parts = path.parts
    if not parts or path.is_absolute() or ".." in parts:
        return False
    if any(p in SKIP_PARTS for p in parts):
        return False
    if path.name.lower() in SKIP_NAMES or path.name.startswith("~$"):
        return False
    if path.suffix.lower() in SKIP_EXTENSIONS:
        return False
    if "secret" in path.name.lower() or "credential" in path.name.lower():
        return False
    if relative in EXACT[repo]:
        return True
    if repo == "TimesSeriesAgent":
        if parts[0] in {"src", "eval", "train", "utils", "tests", "dashbord"}:
            return path.suffix.lower() in {".py", ".md"}
        if parts[0] == "modelos":
            return path.suffix.lower() in {".py", ".pt", ".csv"}
        if parts[0] == "data":
            return path.suffix.lower() in {".csv", ".json", ".md"}
        if parts[0] == "output_noticias":
            return path.suffix.lower() in {".json", ".csv"}
        if parts[0] == "artigo":
            return path.suffix.lower() in {".tex", ".bib", ".md", ".txt", ".pdf", ".png", ".jpg"}
    if repo == "cotacaopython":
        if parts[0] == "util":
            return len(parts) > 1 and parts[1] == "populate" and path.suffix.lower() in {".py", ".sql"}
        if len(parts) == 1:
            return path.suffix.lower() == ".py"
        if parts[0] == "statistica":
            return path.suffix.lower() in {".py", ".ipynb", ".csv", ".tsv"}
        if parts[0] == "bi":
            return path.suffix.lower() in {".csv", ".tsv", ".xlsx"} and "carteira" not in path.name.lower()
    if repo == "analise_fundamental":
        return (len(parts) == 1 and path.suffix.lower() in {".py", ".ipynb"}) or relative == "util/StringTransform.py"
    if repo == "Projeto_ciencia_de_dados_acoes":
        return parts[0] == "data" and path.suffix.lower() in {".xls", ".xlsx"}
    if repo == "cienciaDeDados":
        return len(parts) == 1 and path.suffix == ".py" and (
            path.stem.startswith("dataAnalitycsParte")
            or path.stem.startswith("statistic")
        )
    return False


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def command(*args: str, cwd: Path | None = None) -> str:
    p = subprocess.run(
        args, cwd=cwd, check=True, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=360,
    )
    return p.stdout.strip()


def sources() -> list[dict]:
    records = json.loads(SOURCES.read_text(encoding="utf-8"))
    if not isinstance(records, list) or set(s["repository"] for s in records) != set(EXACT):
        raise ValueError("Conjunto de repositorios inesperado na configuracao.")
    for item in records:
        if item["branch"] not in {"main", "master"}:
            raise ValueError("Branch original invalida.")
        if len(item["sha"]) != 40 or not all(c in "0123456789abcdef" for c in item["sha"]):
            raise ValueError("SHA de origem invalido.")
    return records


def migrate() -> dict:
    DEST.mkdir(parents=True, exist_ok=True)
    manifest = {
        "format_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "storage": "archive_only_not_imported_by_fastapi",
        "sources": [],
    }
    with tempfile.TemporaryDirectory(prefix="cotacoes-legacy-") as temp:
        for item in sources():
            name = item["repository"]
            remote = "https://github.com/0rakul0/" + name + ".git"
            checkout = Path(temp) / name
            print("Clonando", remote, flush=True)
            command("git", "clone", "--quiet", "--depth", "1",
                    "--single-branch", "--branch", item["branch"], remote, str(checkout))
            actual = command("git", "rev-parse", "HEAD", cwd=checkout)
            if actual != item["sha"]:
                raise RuntimeError(
                    f"Origem {name} mudou: esperado {item['sha']}, obtido {actual}. "
                    "Revisar manualmente antes da migracao."
                )
            tracked = command("git", "ls-files", "-z", cwd=checkout).split("\0")
            included = []
            excluded = []
            count = 0
            bytes_total = 0
            for relative in tracked:
                if not relative:
                    continue
                src = checkout / relative
                if not eligible(name, relative):
                    excluded.append({"path": relative, "reason": "outside_financial_archive_scope"})
                    continue
                if not src.is_file() or src.is_symlink():
                    excluded.append({"path": relative, "reason": "not_regular_file"})
                    continue
                size = src.stat().st_size
                if size > MAX_PER_FILE:
                    excluded.append({"path": relative, "reason": "file_too_large"})
                    continue
                dst = DEST / name / relative
                dst.parent.mkdir(parents=True, exist_ok=True)
                if not dst.exists() or sha256(dst) != sha256(src):
                    shutil.copy2(src, dst)
                included.append({"source_path": relative, "archive_path": str(dst.relative_to(ROOT)).replace(os.sep, "/"),
                                 "size": size, "sha256": sha256(dst)})
                count += 1
                bytes_total += size
            manifest["sources"].append({
                "repository": name,
                "url": remote.removesuffix(".git"),
                "branch": item["branch"], "source_commit": actual,
                "archive_files": count, "archive_bytes": bytes_total,
                "included": included, "excluded": excluded,
                "complete_repository_backup": False,
            })
            print(f"Arquivados {name}: {count} arquivos, {bytes_total:,} bytes;", 
                  f"{len(excluded)} arquivos fora do escopo", flush=True)

    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    verify()
    print("Snapshot arquivado e hashes conferidos em", MANIFEST)
    return manifest


def verify() -> None:
    if not MANIFEST.exists():
        raise FileNotFoundError(f"Manifesto ausente: {MANIFEST}")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    expected = {s["repository"]: s["sha"] for s in sources()}
    archive = {}
    for src in manifest.get("sources", []):
        name = src["repository"]
        if name not in expected or expected[name] != src["source_commit"]:
            raise ValueError(f"Fonte divergente: {name}")
        for row in src["included"]:
            relative = row["archive_path"]
            file = ROOT / relative
            if not file.is_relative_to(DEST):
                raise ValueError(f"Arquivo fora do arquivo legado: {relative}")
            if not file.is_file() or file.stat().st_size != row["size"] or sha256(file) != row["sha256"]:
                raise ValueError(f"Arquivo de origem alterado ou ausente: {relative}")
            archive[relative] = row["sha256"]
        if src["archive_files"] != len(src["included"]):
            raise ValueError(f"Contagem divergente: {name}")
    if set(expected) != {row["repository"] for row in manifest.get("sources", [])}:
        raise ValueError("Faltam fontes no manifesto.")
    print(f"Integridade aprovada: {len(archive)} arquivos preservados de {len(expected)} repositorios.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true",
                        help="Verifica os hashes do snapshot sem acessar a rede.")
    args = parser.parse_args()
    if args.verify_only:
        verify()
    else:
        migrate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
