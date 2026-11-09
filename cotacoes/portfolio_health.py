"""Investigacao documental de fundos imobiliarios e FIAGROs.

Snapshots versionados com rastreabilidade a documentos. O risco e uma regra de
triagem, NAO uma estimativa de probabilidade. Informacao nao divulgada permanece
desconhecida. Vacancia se aplica a imoveis de renda; CRI/CRA/permuta usam
criterios de credito e de execucao de empreendimentos.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date
from urllib.parse import urlparse

from cotacoes import market, storage

CATEGORIES = {"CRI", "CRA", "FII", "FIAGRO", "PERMUTA", "IMOVEL", "DEBENTURE", "LCI", "OUTRO"}
LEVELS = ("sem_avaliacao", "monitoramento", "atencao", "critico")
INCIDENT_LEVELS = {
    "recuperacao_judicial": "critico",
    "provisao_integral": "critico",
    "inadimplencia_confirmada": "critico",
    "execucao_garantias": "atencao",
    "carencia_negociada": "atencao",
    "reestruturacao": "atencao",
    "atraso_obra_confirmado": "atencao",
    "violacao_covenant": "atencao",
    "pagamento_atrasado": "atencao",
    "aumento_vacancia": "monitoramento",
    "contrato_encerrando": "monitoramento",
    "outro": "monitoramento",
}
ALLOWED_HOSTS = {"fnet.bmfbovespa.com.br", "www.xpasset.com.br", "xpasset.com.br", "api.mziq.com"}
KINDS = {"relatorio_gerencial", "aviso_rendimentos", "informe", "fato_relevante",
         "termo_securitizacao", "relatorio_securitizadora", "relatorio_fii_investido",
         "outro"}
VERIFICATIONS = {"conferido", "revisao_pendente"}
FREQUENCIES = {"mensal", "trimestral", "semestral", "anual", "irregular", "nao_informada"}


def initialize() -> None:
    with storage.connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS fund_research_snapshots (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          symbol TEXT NOT NULL,
          as_of TEXT NOT NULL,
          published_at TEXT NOT NULL,
          status TEXT NOT NULL CHECK(status IN ('conferido','revisao_pendente')),
          payload_sha256 TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          imported_at TEXT NOT NULL,
          UNIQUE(symbol, as_of, payload_sha256)
        );
        CREATE INDEX IF NOT EXISTS ix_fund_research_snapshots
          ON fund_research_snapshots(symbol, as_of DESC, id DESC);
        """)


def _valid_url(url: str) -> bool:
    try:
        u = urlparse(url)
        return (u.scheme == "https" and u.hostname in ALLOWED_HOSTS and not u.username
                and not u.password and u.port in (None, 443))
    except ValueError:
        return False


def _day(value: str, key: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except (ValueError, TypeError):
        raise ValueError(f"Data invalida em {key}: usar AAAA-MM-DD.") from None


def _month(value: str | None, key: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) != 7 or value[4] != "-":
        raise ValueError(f"{key} requer AAAA-MM ou null.")
    try:
        date.fromisoformat(value + "-01")
    except ValueError:
        raise ValueError(f"{key} requer mes valido.") from None
    return value


def _optional_number(value, key: str, minimum: float = 0, maximum: float = 1e14):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{key} deve ser numero.")
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{key} deve ser numero.") from None
    if not math.isfinite(v) or not minimum <= v <= maximum:
        raise ValueError(f"{key} fora da faixa.")
    return v


def validate(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Snapshot deve ser objeto JSON.")
    symbol = market.normalize_symbol(payload.get("symbol"))
    as_of = _day(payload.get("as_of"), "as_of")
    published = _day(payload.get("published_at"), "published_at")
    if published < as_of:
        raise ValueError("Relatorio nao pode ter sido publicado antes da data de referencia.")
    if payload.get("status") not in VERIFICATIONS:
        raise ValueError("Status de verificacao ausente ou invalido.")
    if payload.get("coverage") not in ("parcial", "completa"):
        raise ValueError("Cobertura deve ser parcial ou completa.")

    docs = payload.get("documents", [])
    holdings = payload.get("holdings", [])
    incidents = payload.get("incidents", [])
    payments = payload.get("payments", [])
    if not all(isinstance(obj, list) for obj in (docs, holdings, incidents, payments)):
        raise ValueError("Documentos, posicoes, eventos e pagamentos devem ser listas.")

    ids = set()
    for doc in docs:
        if not isinstance(doc, dict) or not doc.get("id") or doc["id"] in ids:
            raise ValueError("Documento duplicado ou sem identificador.")
        if doc.get("kind") not in KINDS or not _valid_url(str(doc.get("url") or "")):
            raise ValueError(f"Documento {doc['id']}: fonte oficial ou tipo invalido.")
        _day(doc.get("published_at"), "documento.publicado")
        ids.add(doc["id"])
    if not ids:
        raise ValueError("Todo snapshot precisa de pelo menos um documento primario.")

    holdings_ids = set()
    for item in holdings:
        if not isinstance(item, dict) or not item.get("id") or item["id"] in holdings_ids:
            raise ValueError("Posicao duplicada ou sem identificador.")
        holdings_ids.add(item["id"])
        if item.get("category") not in CATEGORIES:
            raise ValueError(f"Categoria de ativo invalida em {item['id']}.")
        if item.get("source") not in ids:
            raise ValueError(f"Posicao {item['id']} sem documento de suporte.")
        if item.get("name") is None or not str(item["name"]).strip():
            raise ValueError("Toda posicao precisa de nome.")
        for field in ("volume_brl_million", "nav_pct", "construction_pct",
                      "sales_pct", "vacancy_pct", "occupancy_pct", "ltv_pct"):
            _optional_number(item.get(field), field, maximum=100 if field.endswith("_pct") else 1e9)
        for field in ("maturity_month", "delivery_month", "lease_expiry_month"):
            _month(item.get(field), field)
        if item.get("periodicity") not in FREQUENCIES:
            raise ValueError("Periodicidade obrigatoria (mesmo que nao informada).")
        if item.get("exact_payment_day") is not None:
            day = item["exact_payment_day"]
            if type(day) is not int or not 1 <= day <= 31:
                raise ValueError("Dia de pagamento precisa estar documentado entre 1 e 31.")
            if item["periodicity"] == "nao_informada":
                raise ValueError("Dia nao pode coexistir com periodicidade desconhecida.")
        if item.get("vacancy_pct") is not None and item["category"] not in {"IMOVEL", "FII", "FIAGRO"}:
            raise ValueError("Vacancia locatícia nao se aplica diretamente a CRI/CRA/permuta.")
    for finding in incidents:
        if finding.get("holding_id") not in holdings_ids:
            raise ValueError("Ocorrencia sem posicao correspondente.")
        if finding.get("kind") not in INCIDENT_LEVELS:
            raise ValueError("Tipo de ocorrencia desconhecido.")
        if finding.get("source") not in ids:
            raise ValueError("Ocorrencia precisa de documento oficial.")
        if not finding.get("summary"):
            raise ValueError("Ocorrencia sem descricao.")
    for event in payments:
        if event.get("source") not in ids:
            raise ValueError("Pagamento sem documento oficial.")
        if event.get("holding_id") is not None and event["holding_id"] not in holdings_ids:
            raise ValueError("Pagamento vinculado a ativo inexistente.")
        if event.get("kind") not in ("rendimento_fundo", "cupom", "amortizacao", "aluguel",
                                      "provento_fii", "outro"):
            raise ValueError("Tipo de pagamento invalido.")
        _day(event.get("payment_date"), "payment_date")
        if event.get("record_date") is not None:
            _day(event["record_date"], "record_date")
        _optional_number(event.get("amount_per_unit"), "amount_per_unit")
    for field in ("result_brl", "distributed_brl", "nav_brl"):
        _optional_number(payload.get("overview", {}).get(field), field)
    allocation = payload.get("overview", {}).get("allocation_pct", {})
    for name, value in allocation.items():
        _optional_number(value, "allocation_pct."+name, maximum=100)
    if sum(allocation.values()) > 100.5:
        raise ValueError("Alocacao declarada ultrapassa 100%.")
    normalized = dict(payload)
    normalized["symbol"] = symbol
    normalized["as_of"] = as_of
    normalized["published_at"] = published
    return normalized


def ingest(payload: dict) -> dict:
    normalized = validate(payload)
    serialized = json.dumps(normalized, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":"), allow_nan=False)
    checksum = hashlib.sha256(serialized.encode()).hexdigest()
    initialize()
    with storage.connection() as conn:
        cursor = conn.execute("""
            INSERT OR IGNORE INTO fund_research_snapshots
            (symbol,as_of,published_at,status,payload_sha256,payload_json,imported_at)
            VALUES(?,?,?,?,?,?,?)
        """, (normalized["symbol"], normalized["as_of"], normalized["published_at"],
              normalized["status"], checksum, serialized, storage.utc_now()))
        row = conn.execute("""
            SELECT id FROM fund_research_snapshots
            WHERE symbol=? AND as_of=? AND payload_sha256=?
        """, (normalized["symbol"], normalized["as_of"], checksum)).fetchone()
    return {"id": row["id"], "symbol": normalized["symbol"],
            "as_of": normalized["as_of"], "sha256": checksum,
            "created": cursor.rowcount > 0}


def latest(symbol: str) -> tuple[dict, dict] | None:
    symbol = market.normalize_symbol(symbol)
    initialize()
    with storage.connection() as conn:
        row = conn.execute("""
            SELECT * FROM fund_research_snapshots WHERE symbol=?
            ORDER BY as_of DESC, id DESC LIMIT 1
        """, (symbol,)).fetchone()
    if not row:
        return None
    return dict(row), json.loads(row["payload_json"])


def _severity(levels: list[str]) -> str:
    return max(levels, key=lambda v: LEVELS.index(v), default="sem_avaliacao")


def _month_past(expected: str | None, as_of: str) -> bool:
    return expected is not None and expected < as_of[:7]


def _holding_flags(item: dict, incidents: list[dict], as_of: str) -> list[dict]:
    findings = []
    for incident in incidents:
        findings.append({
            "severity": INCIDENT_LEVELS[incident["kind"]],
            "code": incident["kind"], "reason": incident["summary"],
            "source": incident["source"], "basis": "evento_documentado",
        })
    category = item["category"]
    construction = item.get("construction_pct")
    sales = item.get("sales_pct")
    delivery = item.get("delivery_month")
    if category == "PERMUTA":
        if construction is not None and construction < 100 and _month_past(delivery, as_of):
            findings.append({"severity": "atencao", "code": "entrega_prevista_ultrapassada",
                             "reason": "Data prevista anterior ao relatorio e obra ainda abaixo de 100%.",
                             "source": item["source"], "basis": "regra_de_triagem"})
        if sales is not None and construction is not None and construction >= 75 and sales < 40:
            findings.append({"severity": "atencao", "code": "estoque_elevado",
                             "reason": "Obra com >=75% de avance e menos de 40% de vendas na data-base.",
                             "source": item["source"], "basis": "regra_de_triagem"})
        elif sales is not None and sales < 40:
            findings.append({"severity": "monitoramento", "code": "vendas_iniciais_baixas",
                             "reason": "Percentual de vendas inferior a 40%; depende do estagio do projeto.",
                             "source": item["source"], "basis": "regra_de_triagem"})
    if category in ("IMOVEL", "FII", "FIAGRO"):
        vacancy = item.get("vacancy_pct")
        if vacancy is not None and vacancy >= 20:
            findings.append({"severity": "atencao", "code": "vacancia_observada",
                             "reason": "Vacancia locaticia divulgada >=20%; nao e previsao probabilistica.",
                             "source": item["source"], "basis": "regra_de_triagem"})
        expiry = item.get("lease_expiry_month")
        if expiry and expiry >= as_of[:7]:
            year, month = map(int, expiry.split("-"))
            now_year, now_month = map(int, as_of[:7].split("-"))
            if 0 <= (year-now_year)*12 + month-now_month <= 12:
                findings.append({"severity": "monitoramento", "code": "vencimento_contrato",
                                 "reason": "Contrato de locacao vence dentro de 12 meses.",
                                 "source": item["source"], "basis": "regra_de_triagem"})
    return findings


def _evaluate(payload: dict, as_of: str) -> list[dict]:
    incidents_by_id: dict[str, list[dict]] = {}
    for incident in payload["incidents"]:
        incidents_by_id.setdefault(incident["holding_id"], []).append(incident)
    exposures = []
    for holding in payload["holdings"]:
        flags = _holding_flags(holding, incidents_by_id.get(holding["id"], []), as_of)
        risk = _severity([f["severity"] for f in flags])
        exposures.append({**holding, "risk": risk, "flags": flags,
                          "has_vacancy_data": holding.get("vacancy_pct") is not None,
                          "has_exact_coupon_day": holding.get("exact_payment_day") is not None})
    return exposures


def report(symbol: str, as_of: str | None = None, category: str | None = None) -> dict:
    result = latest(symbol)
    if result is None:
        return {"symbol": market.normalize_symbol(symbol), "status": "sem_documentos",
                "coverage": None, "exposures": [], "findings": [],
                "note": "Nenhum documento oficial foi importado e revisado para este ativo."}
    row, snapshot = result
    evaluated_at = _day(as_of, "as_of") if as_of else date.today().isoformat()
    holdings = _evaluate(snapshot, snapshot["as_of"])
    if category:
        if category not in CATEGORIES:
            raise ValueError("Tipo de ativo invalido.")
        holdings = [h for h in holdings if h["category"] == category]
    critical = [h for h in holdings if h["risk"] == "critico"]
    warnings = [h for h in holdings if h["risk"] == "atencao"]
    incomplete = [
        h["id"] for h in holdings if (h["category"] in {"CRI", "CRA"}
        and (h.get("maturity_month") is None or h.get("exact_payment_day") is None))
    ]
    cash = snapshot.get("overview", {})
    result_cash = cash.get("result_brl")
    distributions = cash.get("distributed_brl")
    coverage_ratio = (round(result_cash / distributions, 4)
                      if result_cash is not None and distributions and distributions > 0 else None)
    age = (date.fromisoformat(evaluated_at) - date.fromisoformat(snapshot["as_of"])).days
    return {
        "symbol": snapshot["symbol"], "status": "analisado",
        "snapshot_id": row["id"], "reference_date": snapshot["as_of"],
        "published_at": snapshot["published_at"], "verified": snapshot["status"],
        "coverage": snapshot["coverage"], "days_since_reference": age,
        "outdated": age > 90, "source_documents": snapshot["documents"],
        "overview": {**cash, "cash_distribution_coverage_ratio": coverage_ratio},
        "summary": {
            "disclosed_holdings": len(holdings), "critical": len(critical),
            "attention": len(warnings),
            "without_exact_coupon_schedule": len(incomplete),
            "with_reported_vacancy": sum(h["has_vacancy_data"] for h in holdings),
        },
        "exposures": holdings,
        "findings": [{"holding_id": h["id"], "name": h["name"],
                      "risk": h["risk"], "flags": h["flags"]}
                     for h in holdings if h["flags"]],
        "note": "Alerta qualitativo de triagem, sem probabilidades. Ausencia de evidencia NAO significa ausencia de risco; dados refletem somente a data-base do relatorio.",
    }


def agenda(symbol: str, as_of: str | None = None) -> dict:
    result = latest(symbol)
    if result is None:
        return {"symbol": market.normalize_symbol(symbol), "payments": [],
                "maturities_by_month": [], "uncertain_coupon_dates": []}
    _, payload = result
    today = _day(as_of, "as_of") if as_of else date.today().isoformat()
    # Nao gera pagamentos mensais ficticios a partir de 'Periodicidade: Mensal'.
    events = sorted(payload["payments"], key=lambda e: e["payment_date"])
    maturities = [
        {"holding_id": h["id"], "name": h["name"], "category": h["category"],
         "maturity_month": h["maturity_month"], "precision": "month_only",
         "source": h["source"]}
        for h in payload["holdings"] if h.get("maturity_month")
    ]
    uncertain = [
        {"holding_id": h["id"], "periodicity": h["periodicity"],
         "reason": "Periodicidade nao define dia exato."}
        for h in payload["holdings"]
        if h["category"] in {"CRI", "CRA"} and h["periodicity"] != "nao_informada"
        and h.get("exact_payment_day") is None
    ]
    return {"symbol": payload["symbol"], "reference_date": payload["as_of"],
            "as_of": today,
            "payments": [{**e, "status": "futuro" if e["payment_date"] > today
                          else "data_de_pagamento_informada"}
                         for e in events],
            "maturities_by_month": sorted(maturities, key=lambda x: x["maturity_month"]),
            "uncertain_coupon_dates": uncertain,
            "note": "Data passada nao comprova pagamento realizado. Vencimento AAAA-MM nao especifica dia. O calendario so inclui datas exatas publicadas.",
            }


def exposure(symbol: str, holding_id: str) -> dict | None:
    report_data = report(symbol)
    return next((x for x in report_data["exposures"] if x["id"] == holding_id), None)
