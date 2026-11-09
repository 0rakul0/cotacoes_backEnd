"""Analise estatistica historica de ativos, sem modelos preditivos.

As series legadas intradiarias sao consolidadas em um unico fechamento por dia.
Os calculos usam retornos, nunca precos brutos, para estimar correlacoes.
"""
from __future__ import annotations

import math
import statistics
from datetime import date, timedelta

from cotacoes import storage


def daily_prices(symbol: str, days: int = 365) -> list[dict]:
    """Escolhe uma cotacao por data; prefere a fonte diaria ao CSV intradiario."""
    if days < 30 or days > 3650:
        raise ValueError("Janela deve ficar entre 30 e 3650 dias.")
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    with storage.connection() as conn:
        rows = conn.execute("""
            SELECT day, close, currency, source FROM (
                SELECT SUBSTR(observed_at, 1, 10) AS day,
                       close, currency, source,
                       ROW_NUMBER() OVER (
                           PARTITION BY SUBSTR(observed_at, 1, 10)
                           ORDER BY CASE WHEN source = 'yfinance' THEN 0 ELSE 1 END,
                                    observed_at DESC
                       ) AS rank_day
                FROM prices
                WHERE symbol = ? AND SUBSTR(observed_at, 1, 10) >= ?
            ) WHERE rank_day = 1 ORDER BY day
        """, (symbol, cutoff)).fetchall()
    prices = [dict(row) for row in rows if math.isfinite(row["close"]) and row["close"] > 0]
    if prices and len({p["currency"] for p in prices}) != 1:
        raise ValueError("Historico contem moedas diferentes; normalize as fontes antes da analise.")
    return prices


def daily_returns(prices: list[dict]) -> dict[str, float]:
    """Ignora saltos superiores a 10 dias para nao mascarar lacunas de coleta."""
    out = {}
    for previous, current in zip(prices, prices[1:]):
        gap = (date.fromisoformat(current["day"]) - date.fromisoformat(previous["day"])).days
        if 0 < gap <= 10:
            out[current["day"]] = current["close"] / previous["close"] - 1.0
    return out


def percentile_tail(returns: list[float], confidence: float) -> dict:
    """VaR e CVaR historicos com a pior cauda discreta de observacoes."""
    if not 0.8 <= confidence <= 0.99:
        raise ValueError("Confianca deve estar entre 0.80 e 0.99.")
    tail_size = max(1, math.ceil(len(returns) * (1 - confidence)))
    worst = sorted(returns)[:tail_size]
    # Perda expressa como percentual positivo (zero se todos os retornos da cauda forem positivos).
    return {
        "var_pct": round(max(0.0, -worst[-1]) * 100, 4),
        "cvar_pct": round(max(0.0, -statistics.mean(worst)) * 100, 4),
        "tail_observations": tail_size,
    }


def metrics_from_prices(prices: list[dict], symbol: str, confidence: float = 0.95) -> dict:
    returns = list(daily_returns(prices).values())
    if len(returns) < 30:
        raise ValueError("Necessarios pelo menos 30 retornos diarios validos para risco.")
    annual_days = 365 if symbol.startswith(("BTC-", "ETH-", "SOL-")) else 252
    vol = statistics.stdev(returns) * math.sqrt(annual_days) * 100
    max_price = 0.0
    drawdown = 0.0
    for point in prices:
        max_price = max(max_price, point["close"])
        drawdown = min(drawdown, point["close"] / max_price - 1)
    tail = percentile_tail(returns, confidence)
    return {
        "symbol": symbol,
        "currency": prices[-1]["currency"],
        "from": prices[0]["day"],
        "to": prices[-1]["day"],
        "observations": len(returns),
        "confidence": confidence,
        "cumulative_price_return_pct": round((prices[-1]["close"] / prices[0]["close"] - 1) * 100, 4),
        "annualized_volatility_pct": round(vol, 4),
        "max_drawdown_pct": round(drawdown * 100, 4),
        "worst_daily_return_pct": round(min(returns) * 100, 4),
        **tail,
        "annualization_days": annual_days,
        "method": "historical_daily_close",
        "note": "VaR/CVaR historicos nao sao limites garantidos. Retornos nao incluem dividendos, custos, impostos nem inflacao.",
    }


def asset_risk(symbol: str, days: int = 365, confidence: float = 0.95) -> dict:
    return metrics_from_prices(daily_prices(symbol, days), symbol, confidence)


def events(symbol: str, days: int = 365, threshold_pct: float = 2.0) -> dict:
    """Detecta dias de variacao expressiva, sem atribuir causalidade a noticias."""
    if not 0.1 <= threshold_pct <= 100.0:
        raise ValueError("Limiar deve estar entre 0.1% e 100%.")
    points = daily_prices(symbol, days)
    returns = daily_returns(points)
    findings = [
        {"date": day, "return_pct": round(ret * 100, 4),
         "direction": "alta" if ret > 0 else "queda"}
        for day, ret in returns.items() if abs(ret) * 100 >= threshold_pct
    ]
    return {
        "symbol": symbol, "days": days, "threshold_pct": threshold_pct,
        "observations": len(returns), "events": list(reversed(findings))[:100],
        "total_events": len(findings),
        "note": "A variacao e um evento estatistico, nao prova relacao com uma noticia.",
    }


def _pearson(a: list[float], b: list[float], min_samples: int = 30) -> float | None:
    if len(a) < min_samples:
        return None
    avg_a = statistics.mean(a)
    avg_b = statistics.mean(b)
    ca = [v - avg_a for v in a]
    cb = [v - avg_b for v in b]
    denom = math.sqrt(sum(v * v for v in ca) * sum(v * v for v in cb))
    return round(sum(x * y for x, y in zip(ca, cb)) / denom, 4) if denom else None


def correlation_matrix(symbols: list[str], days: int = 365, rolling_days: int = 30) -> dict:
    if not 2 <= len(symbols) <= 12 or len(set(symbols)) != len(symbols):
        raise ValueError("Informe entre 2 e 12 tickers distintos.")
    if not 20 <= rolling_days <= 252:
        raise ValueError("Janela de correlacao movel deve ficar entre 20 e 252.")
    series = {symbol: daily_prices(symbol, days) for symbol in symbols}
    returns = {symbol: daily_returns(points) for symbol, points in series.items()}
    currency = {symbol: points[-1]["currency"] if points else None for symbol, points in series.items()}
    pairs = []
    for i, left in enumerate(symbols):
        for right in symbols[i + 1:]:
            common = sorted(set(returns[left]) & set(returns[right]))
            if currency[left] is None or currency[right] is None or currency[left] != currency[right]:
                pairs.append({
                    "left": left, "right": right, "currency": None,
                    "observations": 0, "correlation": None, "rolling_correlation": None,
                    "warning": "Ativos sem dados ou em moedas diferentes.",
                })
                continue
            aa = [returns[left][d] for d in common]
            bb = [returns[right][d] for d in common]
            pairs.append({
                "left": left, "right": right, "currency": currency[left],
                "observations": len(common),
                "correlation": _pearson(aa, bb),
                "rolling_correlation": _pearson(aa[-rolling_days:], bb[-rolling_days:], min_samples=max(20, min(30, rolling_days))),
                "warning": None if len(common) >= 30 else "Menos de 30 dias de retornos em comum.",
            })
    return {"symbols": symbols, "days": days, "rolling_days": rolling_days,
            "pairs": pairs, "method": "Pearson_daily_returns_same_currency"}


def portfolio_risk(positions: list[dict], days: int = 365, confidence: float = 0.95) -> dict:
    """Carteira de pesos atuais constantes; nao reconstrucao da carteira historica."""
    groups: dict[str, list[tuple[str, float]]] = {}
    skipped = []
    for position in positions:
        if position["quantity"] <= 0 or position["market_value"] is None:
            skipped.append(position["symbol"])
            continue
        groups.setdefault(position["currency"], []).append(
            (position["symbol"], position["market_value"]))
    out = []
    for currency, members in sorted(groups.items()):
        values = {symbol: value for symbol, value in members}
        total = sum(values.values())
        series = {symbol: daily_returns(daily_prices(symbol, days)) for symbol in values}
        common = set.intersection(*(set(s) for s in series.values()))
        aligned = sorted(common)
        if total <= 0 or len(aligned) < 30:
            out.append({"currency": currency, "observations": len(aligned),
                        "risk": None, "warning": "Historico insuficiente para estimar risco da carteira."})
            continue
        results = [sum(series[symbol][day] * value / total for symbol, value in values.items())
                   for day in aligned]
        tail = percentile_tail(results, confidence)
        out.append({
            "currency": currency, "observations": len(results),
            "weights": [{"symbol": symbol, "weight_pct": round(value / total * 100, 4)}
                        for symbol, value in members],
            "annualized_volatility_pct": round(statistics.stdev(results) * math.sqrt(252) * 100, 4),
            "worst_daily_return_pct": round(min(results) * 100, 4),
            **tail, "risk": "historical_constant_weights", "warning": None,
        })
    return {
        "by_currency": out, "skipped_positions": skipped, "confidence": confidence,
        "note": "Estimativa hipotetica a pesos atuais fixos, sem historico de rebalanceamento, custos e dividendos. Nao representa desempenho realizado.",
    }
