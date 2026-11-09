"""Treinamento isolado por ticker com validacao e teste cronologicos.

O baseline e a persistencia sao leves; modelos PyTorch sao opcionais e
so sao importados explicitamente durante treino/inferencia neural.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
from datetime import date, timedelta

import numpy as np

from cotacoes import analysis, market, model_registry, storage

MIN_CLOSES = 260
DEFAULT_WINDOW = 20


def prepare(symbol: str, days: int = 1825, window: int = DEFAULT_WINDOW) -> dict:
    if days < 365 or days > 3650:
        raise ValueError("O treinamento requer entre 365 e 3650 dias de consulta.")
    if window < 5 or window > 60:
        raise ValueError("Janela deve ficar entre 5 e 60 observacoes.")
    points = analysis.daily_prices(symbol, days)
    if not points:
        raise ValueError(f"Sem cotacoes historicas de {symbol}; atualize o ativo antes do treino.")
    # Mantem apenas o segmento final: nunca atravessa lacunas de anos nos CSVs legados.
    segment = [points[-1]]
    for previous in reversed(points[:-1]):
        gap = (date.fromisoformat(segment[0]["day"]) - date.fromisoformat(previous["day"])).days
        if not 0 < gap <= 10:
            break
        segment.insert(0, previous)
    if len(segment) < max(MIN_CLOSES, window + 80):
        raise ValueError(
            f"Historico continuo insuficiente para {symbol}: {len(segment)} fechamentos. "
            f"Minimo: {max(MIN_CLOSES, window + 80)}."
        )
    closes = np.array([float(p["close"]) for p in segment], dtype=np.float64)
    if not np.all(np.isfinite(closes)) or np.any(closes <= 0):
        raise ValueError("Precos invalidos.")
    returns = np.diff(np.log(closes))
    # X termina em preco[t]; y representa retorno de t para t+1.
    X = np.stack([returns[i - window:i] for i in range(window, len(returns))])
    y = returns[window:]
    target_dates = [p["day"] for p in segment[window + 1:]]
    if X.shape[0] != len(target_dates):
        raise RuntimeError("Alinhamento temporal de features falhou.")

    n = len(y)
    train_end = int(n * 0.70)
    val_end = int(n * 0.85)
    if train_end < 140 or val_end - train_end < 25 or n - val_end < 25:
        raise ValueError("Amostra insuficiente para treino, validacao e teste independentes.")
    mean = float(y[:train_end].mean())
    std = float(y[:train_end].std())
    std = max(std, 1e-6)
    fingerprint_data = {
        "feature_version": "univariate_log_returns_v1",
        "window": window,
        "close_history": [
            [p["day"], round(float(p["close"]), 10), p["currency"], p["source"]]
            for p in segment
        ],
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_data, ensure_ascii=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "symbol": symbol, "window": window, "days": days,
        "X": X, "y": y, "dates": target_dates,
        "train_end": train_end, "val_end": val_end,
        "mean": mean, "std": std,
        "currency": segment[-1]["currency"],
        "data_end": segment[-1]["day"], "data_start": segment[0]["day"],
        "fingerprint": fingerprint, "latest_close": float(closes[-1]),
    }


def _metric(y: np.ndarray, pred: np.ndarray) -> dict:
    if len(y) == 0 or not np.all(np.isfinite(pred)):
        raise ValueError("Predicoes ausentes ou nao finitas.")
    diff = pred - y
    return {
        "rmse_pct": round(float(np.sqrt(np.mean(diff ** 2)) * 100), 6),
        "mae_pct": round(float(np.mean(np.abs(diff)) * 100), 6),
        "naive_rmse_pct": round(float(np.sqrt(np.mean(y ** 2)) * 100), 6),
        "naive_mae_pct": round(float(np.mean(np.abs(y)) * 100), 6),
        "directional_accuracy_pct": round(float(np.mean(np.sign(pred) == np.sign(y)) * 100), 2),
        "samples": int(len(y)),
    }


def _fit_ridge(X: np.ndarray, y: np.ndarray, alpha: float) -> np.ndarray:
    # X e y padronizados por medias e desvios SOMENTE do treino.
    features = np.column_stack((np.ones(len(X)), X))
    reg = np.eye(features.shape[1]) * alpha
    reg[0, 0] = 0
    return np.linalg.solve(features.T @ features + reg, features.T @ y)


def train_ridge(prepared: dict) -> tuple[dict, dict, bytes | None]:
    ntrain, nval = prepared["train_end"], prepared["val_end"]
    mu, sd = prepared["mean"], prepared["std"]
    normalized = (prepared["X"] - mu) / sd
    target = (prepared["y"] - mu) / sd
    # Hiperparametros selecionados pela validacao, nunca pelo conjunto de teste.
    best = None
    for alpha in (0.1, 1.0, 10.0, 100.0, 1000.0):
        weights = _fit_ridge(normalized[:ntrain], target[:ntrain], alpha)
        prediction = np.column_stack((
            np.ones(nval - ntrain), normalized[ntrain:nval]
        )) @ weights * sd + mu
        score = float(np.mean((prediction - prepared["y"][ntrain:nval]) ** 2))
        if best is None or score < best[0]:
            best = (score, alpha, weights)
    _, alpha, weights = best
    def predict(X: np.ndarray) -> np.ndarray:
        z = (X - mu) / sd
        return np.column_stack((np.ones(len(z)), z)) @ weights * sd + mu
    artifact = {
        "schema": 1,
        "feature": "univariate_log_returns_v1",
        "window": prepared["window"],
        "mean": mu, "std": sd,
        "weights": [float(w) for w in weights],
        "alpha": alpha,
        "currency": prepared["currency"],
        "fingerprint": prepared["fingerprint"],
        "data_end": prepared["data_end"],
        "train_until": prepared["dates"][ntrain - 1],
    }
    metrics = {
        "validation": _metric(prepared["y"][ntrain:nval], predict(prepared["X"][ntrain:nval])),
        "test": _metric(prepared["y"][nval:], predict(prepared["X"][nval:])),
        "method": "one_step_ahead_log_return",
        "baseline": "last_close_zero_return",
    }
    return artifact, metrics, None


def train(symbol: str, family: str = "ridge", days: int = 1825,
          window: int = DEFAULT_WINDOW, epochs: int = 60) -> dict:
    if family not in model_registry.FAMILIES:
        raise ValueError("Familia de modelo invalida.")
    symbol = market.normalize_symbol(symbol)
    if not storage.asset_exists(symbol):
        raise ValueError("Ativo nao acompanhado.")
    dataset = prepare(symbol, days, window)
    if family == "ridge":
        artifact, metrics, weight_bytes = train_ridge(dataset)
    else:
        from cotacoes.torch_forecast import train_neural
        artifact, metrics, weight_bytes = train_neural(dataset, family, epochs, _metric)
    model_registry.initialize()
    run_id = model_registry.save_model(symbol, family, artifact, {
        "fingerprint": dataset["fingerprint"],
        "data_end": dataset["data_end"],
        "currency": dataset["currency"],
        "train_samples": dataset["train_end"],
        "validation_samples": dataset["val_end"] - dataset["train_end"],
        "test_samples": len(dataset["y"]) - dataset["val_end"],
        "metrics": metrics,
    }, weight_bytes)
    chosen = model_registry.choose(symbol, dataset["fingerprint"])
    return {
        "symbol": symbol, "family": family, "model_id": run_id,
        "data_end": dataset["data_end"], "metrics": metrics,
        "selected_family": chosen["family"] if chosen else (
            model_registry.overview(symbol)["selected"] or {}
        ).get("family"),
        "selected": chosen is not None and chosen["id"] == run_id,
    }


def _predict_return(artifact: dict, window_returns: np.ndarray) -> float:
    mu, sd = float(artifact["mean"]), float(artifact["std"])
    if artifact["family"] == "ridge":
        weights = np.array(artifact["weights"], dtype=np.float64)
        normalized = (window_returns - mu) / sd
        return float(np.dot(np.r_[1.0, normalized], weights) * sd + mu)
    from cotacoes.torch_forecast import predict_neural
    return predict_neural(artifact, window_returns)


def _next_session(last: str, symbol: str) -> str:
    day = date.fromisoformat(last) + timedelta(days=1)
    if symbol.endswith(("-BRL", "-USD")):
        return day.isoformat()
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day.isoformat()


def forecast(symbol: str) -> dict:
    """Inferencia de 1 passo; nao chama rede nem executa treinamento."""
    symbol = market.normalize_symbol(symbol)
    row = model_registry.selected(symbol)
    if row is None:
        raise ValueError("Nenhum modelo validado para este ativo. Execute treinamento offline.")
    artifact = model_registry.load_artifact(row)
    window = int(artifact["window"])
    # Serie recente pode conter novos dias; nunca usar retornos de outros tickers.
    prices = analysis.daily_prices(symbol, 3650)
    segment = [prices[-1]] if prices else []
    for previous in reversed(prices[:-1]):
        gap = (date.fromisoformat(segment[0]["day"]) - date.fromisoformat(previous["day"])).days
        if not 0 < gap <= 10:
            break
        segment.insert(0, previous)
    if len(segment) < window + 1:
        raise ValueError("Dados recentes insuficientes para inferencia.")
    latest = segment[-1]
    if latest["currency"] != row["currency"]:
        raise ValueError("Moeda do modelo diverge da cotacao atual.")
    # Na origem, modelos foram avaliados em um dataset definido; avisar sobre staleness.
    lag_days = (date.fromisoformat(latest["day"]) - date.fromisoformat(row["data_end"])).days
    if lag_days < 0:
        raise ValueError("Modelo treinado com cotacoes posteriores ao ultimo preco disponivel.")
    if (date.today() - date.fromisoformat(latest["day"])).days > 14:
        raise ValueError("Cotacao desatualizada; atualize os precos antes da inferencia.")
    returns = np.diff(np.log([p["close"] for p in segment[-window - 1:]]))
    prediction = _predict_return(artifact, returns)
    if not math.isfinite(prediction):
        raise ValueError("Previsao do modelo invalida.")
    # Limita exponenciacao numericamente. Variacoes irreais sao erro de inferencia.
    if abs(prediction) > math.log(2):
        raise ValueError("Previsao fora da faixa operacional; revisar treinamento.")
    last_price = float(latest["close"])
    return {
        "symbol": symbol, "family": row["family"], "model_id": row["id"],
        "trained_at": row["trained_at"], "trained_data_end": row["data_end"],
        "latest_price_date": latest["day"],
        "forecast_for": _next_session(latest["day"], symbol),
        "currency": latest["currency"], "last_close": round(last_price, 6),
        "predicted_log_return_pct": round(prediction * 100, 4),
        "predicted_next_close": round(last_price * math.exp(prediction), 6),
        "stale_model": lag_days > 14,
        "evaluation": json.loads(row["metrics_json"])["test"],
        "note": "Previsao experimental de um fechamento, sem garantia de acerto e sem ajuste de dividendos. Data estimada nao considera feriados.",
    }
