"""Coleta segura e extracao preliminar de documentos oficiais para revisao humana.

Nao coloca documentos brutos ou PDFs antigos no Git. O extrator NAO transforma
frases automaticamente em fatos confirmados, pois tabelas de PDFs variam muito.
O arquivo de staging organiza paginas, hashes e candidatos a investigacao.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from cotacoes import market, portfolio_health, storage

MAX_SIZE = 35 * 1024 * 1024
KEYWORDS = (
    "cri", "cra", "fii", "permuta", "securitizadora", "recebiveis",
    "devedor", "inadimplencia", "recuperacao judicial", "carencia",
    "vencimento", "amortizacao", "pagamento", "provento", "obras",
    "entrega", "habite-se", "vacancia", "ocupacao", "locacao", "vendas",
    "distrato", "ltv", "garantia", "consolidacao", "covenant",
)
CODE_PATTERN = re.compile(r"(?<![0-9A-Z])(?:\d{2}[A-Z]\d{7,8})(?![0-9A-Z])")


def data_root() -> Path:
    return Path(os.getenv("COTACOES_DOCUMENT_DIR",
                    str(storage.ROOT / "data" / "official_documents"))).expanduser().resolve()


def _canonical(url: str) -> str:
    if not portfolio_health._valid_url(url):
        raise ValueError("Somente HTTPS de dominio oficial previamente autorizado.")
    value = urllib.parse.urlparse(url)
    if value.hostname == "fnet.bmfbovespa.com.br":
        if not value.path.startswith("/fnet/publico/exibirDocumento"):
            raise ValueError("Rota do FNET nao autorizada.")
        q = urllib.parse.parse_qs(value.query)
        ids = q.get("id", [])
        if len(ids) != 1 or not ids[0].isdigit():
            raise ValueError("FNET requer um ID numerico.")
    return url


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Nao seguir redirecionamento para host arbitrario.
        raise ValueError("Redirecionamento bloqueado; verifique a origem manualmente.")


def fetch_pdf(symbol: str, url: str) -> dict:
    symbol = market.normalize_symbol(symbol)
    url = _canonical(url)
    opener = urllib.request.build_opener(_NoRedirect)
    request = urllib.request.Request(url, headers={
        "User-Agent": "cotacoes-document-research/0.1 (personal analysis)",
        "Accept": "application/pdf",
    })
    with opener.open(request, timeout=25) as response:
        length = response.headers.get("Content-Length")
        if length and int(length) > MAX_SIZE:
            raise ValueError("PDF oficial maior do que limite permitido.")
        content = response.read(MAX_SIZE + 1)
    if len(content) > MAX_SIZE or not content.startswith(b"%PDF"):
        raise ValueError("Resposta nao e PDF valido ou excede limite.")
    checksum = hashlib.sha256(content).hexdigest()
    base = data_root() / symbol
    base.mkdir(parents=True, exist_ok=True)
    path = base / (checksum[:24] + ".pdf")
    if not path.exists():
        path.write_bytes(content)
    return {"symbol": symbol, "url": url, "sha256": checksum,
            "size": len(content), "local_pdf": str(path),
            "status": "downloaded_unreviewed"}


def extract_pdf(symbol: str, pdf_path: Path, source_url: str,
                reference_date: str, published_at: str) -> dict:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("Instale PyMuPDF: pip install -r requirements-documents.txt") from exc
    symbol = market.normalize_symbol(symbol)
    source_url = _canonical(source_url)
    portfolio_health._day(reference_date, "reference_date")
    portfolio_health._day(published_at, "published_at")
    if published_at < reference_date:
        raise ValueError("Documento publicado antes de sua data de referencia.")
    path = Path(pdf_path).expanduser().resolve()
    if not path.is_file() or path.stat().st_size > MAX_SIZE:
        raise ValueError("PDF ausente ou maior que o limite.")
    raw = path.read_bytes()
    if not raw.startswith(b"%PDF"):
        raise ValueError("Arquivo nao parece ser um PDF.")
    checksum = hashlib.sha256(raw).hexdigest()
    pdf = fitz.open(stream=raw, filetype="pdf")
    if pdf.is_encrypted:
        raise ValueError("PDF protegido; nao tentar quebra de senha.")
    if pdf.page_count > 250:
        raise ValueError("PDF tem paginas demais para extracao automatica.")
    pages = []
    codes = {}
    hits = []
    for i, page in enumerate(pdf):
        body = page.get_text("text", sort=True)
        # Sem OCR automatico. Se corpo for vazio, marcar revisao manual.
        matches = sorted(set(CODE_PATTERN.findall(body)))
        for code in matches:
            codes.setdefault(code, []).append(i + 1)
        line_hits = []
        for line in body.splitlines():
            trimmed = line.strip()
            clean = (trimmed.lower().replace("ê", "e").replace("ç", "c")
                     .replace("ã", "a").replace("á", "a").replace("â", "a")
                     .replace("ó", "o").replace("í", "i"))
            if len(trimmed) >= 5 and any(word in clean for word in KEYWORDS):
                line_hits.append(trimmed[:260])
        pages.append({
            "page": i + 1, "characters": len(body),
            "text": body[:220000], "codes": matches,
            "signal_lines": line_hits[:100],
            "needs_ocr_or_manual_review": len(body.strip()) < 80,
        })
        for line in line_hits[:100]:
            hits.append({"page": i + 1, "text": line})
    staged = {
        "schema_version": 1, "symbol": symbol, "source_url": source_url,
        "reference_date": reference_date, "published_at": published_at,
        "sha256": checksum, "page_count": pdf.page_count,
        "status": "review_pending",
        "security_codes": [{"code": code, "pages": page_list}
                           for code, page_list in sorted(codes.items())],
        "signals": hits, "pages": pages,
        "note": "Evidencias candidatas. Rever no PDF original e estruturar manualmente posicoes, vencimentos e riscos antes de importar no banco.",
    }
    base = data_root() / symbol
    base.mkdir(parents=True, exist_ok=True)
    target = base / (checksum[:24] + ".staging.json")
    target.write_text(json.dumps(staged, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    return {"symbol": symbol, "source_url": source_url, "sha256": checksum,
            "pages": pdf.page_count, "security_codes": len(codes),
            "signal_lines": len(hits), "staging_file": str(target)}


def import_reviewed(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return portfolio_health.ingest(data)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    seed = sub.add_parser("import", help="Importar JSON estruturado revisado (sem rede).")
    seed.add_argument("--file", type=Path, required=True)
    fetch = sub.add_parser("fetch", help="Baixar PDF em HTTPS oficial.")
    fetch.add_argument("--symbol", required=True)
    fetch.add_argument("--url", required=True)
    scan = sub.add_parser("extract", help="Gerar staging de paginas, sem aprovar fatos.")
    scan.add_argument("--symbol", required=True)
    scan.add_argument("--pdf", type=Path, required=True)
    scan.add_argument("--url", required=True)
    scan.add_argument("--reference-date", required=True)
    scan.add_argument("--published-at", required=True)
    args = parser.parse_args(argv)
    if args.action == "import":
        result = import_reviewed(args.file)
    elif args.action == "fetch":
        result = fetch_pdf(args.symbol, args.url)
    else:
        result = extract_pdf(
            args.symbol, args.pdf, args.url, args.reference_date, args.published_at
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
