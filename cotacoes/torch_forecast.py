"""Modelos PyTorch treinados individualmente por ticker.

Adapta as tres arquiteturas do TimesSeriesAgent para retornos univariados e
janelas temporais sem ajustar normalizadores sobre a validacao/teste.
Importar este modulo e opcional; o backend base nao depende de PyTorch.
"""
from __future__ import annotations

import copy
import io
import math

import numpy as np
import torch
from torch import nn

from cotacoes import model_registry


class LSTMReturns(nn.Module):
    def __init__(self, hidden: int = 32):
        super().__init__()
        self.lstm = nn.LSTM(1, hidden, batch_first=True)
        self.fc = nn.Linear(hidden, 1)

    def forward(self, x):
        out, _ = self.lstm(x)
        return self.fc(out[:, -1, :])


class AutoencoderReturns(nn.Module):
    def __init__(self, hidden: int = 32):
        super().__init__()
        self.encoder = nn.LSTM(1, hidden, batch_first=True)
        self.decoder = nn.LSTM(hidden, hidden, batch_first=True)
        self.reconstruction = nn.Linear(hidden, 1)
        self.forecast_head = nn.Linear(hidden, 1)

    def forward(self, x):
        enc, _ = self.encoder(x)
        z = enc[:, -1, :]
        dec, _ = self.decoder(z.unsqueeze(1).expand(-1, x.shape[1], -1))
        return self.forecast_head(z), self.reconstruction(dec)


class TransformerReturns(nn.Module):
    def __init__(self, window: int, hidden: int = 32):
        super().__init__()
        self.input_proj = nn.Linear(1, hidden)
        self.positions = nn.Embedding(window, hidden)
        layer = nn.TransformerEncoderLayer(
            d_model=hidden, nhead=4, dim_feedforward=64,
            dropout=0.1, batch_first=True,
        )
        self.encoder = nn.TransformerEncoder(layer, num_layers=2)
        self.head = nn.Linear(hidden, 1)

    def forward(self, x):
        positions = torch.arange(x.shape[1], device=x.device)
        features = self.input_proj(x) + self.positions(positions).unsqueeze(0)
        encoded = self.encoder(features)
        return self.head(encoded[:, -1, :])


def make_model(family: str, window: int, hidden: int = 32) -> nn.Module:
    if family == "lstm":
        return LSTMReturns(hidden)
    if family == "autoencoder":
        return AutoencoderReturns(hidden)
    if family == "transformer":
        return TransformerReturns(window, hidden)
    raise ValueError("Familia neural desconhecida.")


def _pred(model: nn.Module, batch: torch.Tensor, family: str) -> torch.Tensor:
    out = model(batch)
    return out[0] if family == "autoencoder" else out


def _batch_loss(model, batch, target, family):
    if family == "autoencoder":
        pred, reconstruction = model(batch)
        return nn.functional.mse_loss(pred, target) + 0.15 * nn.functional.mse_loss(reconstruction, batch)
    return nn.functional.mse_loss(model(batch), target)


def train_neural(dataset: dict, family: str, epochs: int, metric_fn) -> tuple[dict, dict, bytes]:
    if family not in ("lstm", "autoencoder", "transformer"):
        raise ValueError("Familia invalida.")
    if epochs < 1 or epochs > 300:
        raise ValueError("Epocha deve estar entre 1 e 300.")
    torch.manual_seed(42)
    torch.set_num_threads(min(2, torch.get_num_threads()))
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    ntrain, nval = dataset["train_end"], dataset["val_end"]
    mu, sd = dataset["mean"], dataset["std"]
    X = ((dataset["X"] - mu) / sd).astype("float32")[:, :, None]
    y = ((dataset["y"] - mu) / sd).astype("float32")[:, None]
    X_train = torch.tensor(X[:ntrain])
    y_train = torch.tensor(y[:ntrain])
    X_val = torch.tensor(X[ntrain:nval], device=device)
    y_val = torch.tensor(y[ntrain:nval], device=device)

    net = make_model(family, dataset["window"]).to(device)
    opt = torch.optim.Adam(net.parameters(), lr=0.001 if family != "transformer" else 0.0005)
    loader = torch.utils.data.DataLoader(
        torch.utils.data.TensorDataset(X_train, y_train),
        batch_size=64, shuffle=True, drop_last=False,
    )
    best_loss = float("inf")
    best_state = None
    no_improvement = 0
    epoch_best = 0
    for epoch in range(epochs):
        net.train()
        for batch, target in loader:
            batch = batch.to(device)
            target = target.to(device)
            opt.zero_grad()
            loss = _batch_loss(net, batch, target, family)
            loss.backward()
            nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            opt.step()
        net.eval()
        with torch.no_grad():
            validation_loss = float(
                nn.functional.mse_loss(_pred(net, X_val, family), y_val)
                .detach().cpu().item()
            )
        if not math.isfinite(validation_loss):
            raise ValueError("Modelo neural gerou perda nao finita.")
        if validation_loss < best_loss - 1e-7:
            best_loss = validation_loss
            best_state = copy.deepcopy(net.state_dict())
            epoch_best = epoch + 1
            no_improvement = 0
        else:
            no_improvement += 1
        if no_improvement >= 10:
            break
    if best_state is None:
        raise ValueError("Falha ao treinar modelo neural.")
    net.load_state_dict(best_state)
    net.eval()
    def predict(arr):
        x = torch.tensor(arr, device=device)
        with torch.no_grad():
            values = _pred(net, x, family).squeeze(-1).cpu().numpy()
        return values.astype("float64") * sd + mu

    val_pred = predict(X[ntrain:nval])
    test_pred = predict(X[nval:])
    metrics = {
        "validation": metric_fn(dataset["y"][ntrain:nval], val_pred),
        "test": metric_fn(dataset["y"][nval:], test_pred),
        "method": "one_step_ahead_log_return",
        "baseline": "last_close_zero_return",
        "trained_epochs": epoch_best,
        "device_used_for_training": str(device),
    }
    saved = io.BytesIO()
    # Apenas state_dict de tensores, sem objetos Python/pickles de scaler antigos.
    torch.save({key: value.detach().cpu() for key, value in best_state.items()}, saved)
    artifact = {
        "schema": 1, "feature": "univariate_log_returns_v1",
        "window": dataset["window"], "mean": mu, "std": sd,
        "hidden_size": 32, "currency": dataset["currency"],
        "fingerprint": dataset["fingerprint"], "data_end": dataset["data_end"],
        "train_until": dataset["dates"][ntrain - 1],
        "format": "pytorch_state_dict_weights_only",
    }
    return artifact, metrics, saved.getvalue()


def predict_neural(artifact: dict, window_returns: np.ndarray) -> float:
    """Somente artefatos gerados pelo worker e verificados por SHA-256."""
    family = artifact["family"]
    if family not in ("lstm", "autoencoder", "transformer"):
        raise ValueError("Familia invalida.")
    if len(window_returns) != artifact["window"]:
        raise ValueError("Comprimento da janela de inferencia nao corresponde ao treino.")
    serialized = model_registry.read_verified(
        artifact["weights_relpath"], artifact["weights_sha256"]
    )
    weights = torch.load(io.BytesIO(serialized), map_location="cpu", weights_only=True)
    model = make_model(family, int(artifact["window"]), int(artifact["hidden_size"]))
    model.load_state_dict(weights, strict=True)
    model.eval()
    values = ((window_returns - artifact["mean"]) / artifact["std"]).astype("float32")
    batch = torch.tensor(values, dtype=torch.float32).reshape(1, -1, 1)
    with torch.no_grad():
        prediction = float(_pred(model, batch, family).item())
    return float(prediction * artifact["std"] + artifact["mean"])
