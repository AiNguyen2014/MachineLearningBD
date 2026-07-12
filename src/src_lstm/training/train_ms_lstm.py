"""Train a multi-source, multi-branch LSTM for daily salinity forecasting.

Dynamic daily salinity and ERA5 variables are encoded by an LSTM. Lagged
monthly Sentinel-2 context, coordinates, and station identity are fused only
after the recurrent encoder. The model predicts a residual from the most recent
available salinity value in the input window.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset


ROOT = Path(__file__).resolve().parent
DEFAULT_DATA = ROOT / "Data/processed/lstm_daily_multisource_2020_2023.csv"

DYNAMIC_SALINITY = [
    "salinity_input", "salinity_input_imputed", "days_since_salinity_observed",
    "salinity_observed", "salinity_qc_invalid", "day_of_year_sin", "day_of_year_cos",
]
DYNAMIC_ERA5 = [
    "temperature_2m_c", "temperature_2m_min_c", "temperature_2m_max_c",
    "dewpoint_temperature_2m_c", "precipitation_mm", "potential_evaporation_mm",
    "runoff_mm", "wind_u_10m_ms", "wind_v_10m_ms", "wind_speed_10m_ms",
    "surface_pressure_hpa", "soil_moisture_layer1_vol", "solar_radiation_mj_m2",
]
S2_CORE = [
    "s2_B3_mean", "s2_B4_mean", "s2_B8_mean", "s2_B11_mean", "s2_B12_mean",
    "s2_NDVI_mean", "s2_NDWI_mean", "s2_MNDWI_mean",
    "s2_s2_valid_image_count", "s2_month_available",
]
CONTEXT = ["lat", "lon", *S2_CORE]


@dataclass
class Config:
    data: str
    output_dir: str
    lookback: int
    horizon: int
    train_end: str
    val_end: str
    batch_size: int
    epochs: int
    patience: int
    lr: float
    weight_decay: float
    hidden_size: int
    context_hidden: int
    fusion_hidden: int
    station_embedding_dim: int
    dropout: float
    grad_clip: float
    seed: int
    use_s2: bool
    use_era5: bool


def args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, default=DEFAULT_DATA)
    p.add_argument("--output-dir", type=Path, default=ROOT / "models/ms_lstm")
    p.add_argument("--lookback", type=int, default=30)
    p.add_argument("--horizon", type=int, default=1)
    p.add_argument("--train-end", default="2021-12-31")
    p.add_argument("--val-end", default="2022-12-31")
    p.add_argument("--batch-size", type=int, default=128)
    p.add_argument("--epochs", type=int, default=80)
    p.add_argument("--patience", type=int, default=10)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--weight-decay", type=float, default=1e-4)
    p.add_argument("--hidden-size", type=int, default=64)
    p.add_argument("--context-hidden", type=int, default=32)
    p.add_argument("--fusion-hidden", type=int, default=64)
    p.add_argument("--station-embedding-dim", type=int, default=8)
    p.add_argument("--dropout", type=float, default=0.15)
    p.add_argument("--grad-clip", type=float, default=1.0)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--no-s2", action="store_true", help="ERA5 ablation without S2 context")
    p.add_argument("--salinity-only", action="store_true", help="LSTM-S ablation without ERA5 or S2")
    return p.parse_args()


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


class Standardizer:
    def fit(self, frame: pd.DataFrame, cols: list[str]) -> None:
        self.cols = cols
        values = frame[cols].replace([np.inf, -np.inf], np.nan)
        self.median = values.median().fillna(0.0)
        filled = values.fillna(self.median)
        self.mean = filled.mean()
        self.std = filled.std().replace(0, 1.0).fillna(1.0)

    def transform(self, frame: pd.DataFrame) -> np.ndarray:
        values = frame[self.cols].replace([np.inf, -np.inf], np.nan).fillna(self.median)
        return ((values - self.mean) / self.std).to_numpy(np.float32)

    def export(self) -> dict:
        return {"columns": self.cols, "median": self.median.to_dict(), "mean": self.mean.to_dict(), "std": self.std.to_dict()}


def split_ok(date: pd.Timestamp, split: str, train_end: pd.Timestamp, val_end: pd.Timestamp) -> bool:
    if split == "train":
        return date <= train_end
    if split == "val":
        return train_end < date <= val_end
    return date > val_end


def windows(
    df: pd.DataFrame, dynamic: np.ndarray, context: np.ndarray, lookback: int,
    horizon: int, split: str, train_end: pd.Timestamp, val_end: pd.Timestamp,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, pd.DataFrame]:
    xs, cs, stations, residuals, baselines, meta = [], [], [], [], [], []
    for station_id, group in df.groupby("station_id", sort=False):
        idx = group.index.to_numpy()
        dates = group.date.to_numpy()
        targets = group.target_salinity_max.to_numpy(np.float32)
        raw_input = group.salinity_input.to_numpy(np.float32)
        station_idx = int(group.station_idx.iloc[0])
        for end in range(lookback - 1, len(group) - horizon):
            target_pos = end + horizon
            target_date = pd.Timestamp(dates[target_pos])
            if not split_ok(target_date, split, train_end, val_end) or np.isnan(targets[target_pos]):
                continue
            start = end - lookback + 1
            recent = raw_input[start : end + 1]
            valid = recent[np.isfinite(recent)]
            if not len(valid):
                continue
            baseline = float(valid[-1])
            window_idx = idx[start : end + 1]
            xs.append(dynamic[window_idx])
            cs.append(context[idx[end]])
            stations.append(station_idx)
            baselines.append(baseline)
            residuals.append(float(targets[target_pos] - baseline))
            meta.append({"station_id": station_id, "target_date": target_date.date().isoformat(),
                         "input_start": pd.Timestamp(dates[start]).date().isoformat(),
                         "input_end": pd.Timestamp(dates[end]).date().isoformat(),
                         "baseline": baseline, "y_true": float(targets[target_pos]), "split": split})
    return (np.stack(xs).astype(np.float32), np.stack(cs).astype(np.float32),
            np.asarray(stations, np.int64), np.asarray(residuals, np.float32)[:, None],
            np.asarray(baselines, np.float32)[:, None], pd.DataFrame(meta))


class Samples(Dataset):
    def __init__(self, x, c, station, residual, baseline):
        self.tensors = tuple(torch.from_numpy(v) for v in (x, c, station, residual, baseline))
    def __len__(self): return len(self.tensors[2])
    def __getitem__(self, i): return tuple(v[i] for v in self.tensors)


class MultiSourceLSTM(nn.Module):
    def __init__(self, n_dynamic, n_context, n_stations, cfg: Config):
        super().__init__()
        self.station_embedding = nn.Embedding(n_stations, cfg.station_embedding_dim)
        self.lstm = nn.LSTM(n_dynamic, cfg.hidden_size, batch_first=True)
        self.context = nn.Sequential(
            nn.Linear(n_context, cfg.context_hidden), nn.LayerNorm(cfg.context_hidden),
            nn.GELU(), nn.Dropout(cfg.dropout),
        )
        fused = cfg.hidden_size + cfg.context_hidden + cfg.station_embedding_dim
        self.head = nn.Sequential(
            nn.Linear(fused, cfg.fusion_hidden), nn.LayerNorm(cfg.fusion_hidden),
            nn.GELU(), nn.Dropout(cfg.dropout), nn.Linear(cfg.fusion_hidden, 1),
        )
    def forward(self, x, context, station):
        sequence, _ = self.lstm(x)
        fused = torch.cat([sequence[:, -1], self.context(context), self.station_embedding(station)], dim=1)
        return self.head(fused)


def score(y, pred):
    error = pred - y
    return {"rmse": float(np.sqrt(np.mean(error**2))), "mae": float(np.mean(np.abs(error))),
            "r2": float(1 - np.sum(error**2) / np.sum((y - y.mean())**2))}


def evaluate(model, loader, device, residual_mean, residual_std):
    model.eval(); predictions, truths = [], []
    with torch.no_grad():
        for x, c, station, residual, baseline in loader:
            pred_residual = model(x.to(device), c.to(device), station.to(device)).cpu().numpy()
            pred = baseline.numpy() + pred_residual * residual_std + residual_mean
            truth = baseline.numpy() + residual.numpy() * residual_std + residual_mean
            predictions.append(pred); truths.append(truth)
    pred, truth = np.vstack(predictions).ravel(), np.vstack(truths).ravel()
    return score(truth, pred), pred, truth


def main() -> None:
    a = args(); set_seed(a.seed); a.output_dir.mkdir(parents=True, exist_ok=True)
    cfg = Config(str(a.data), str(a.output_dir), a.lookback, a.horizon, a.train_end, a.val_end,
                 a.batch_size, a.epochs, a.patience, a.lr, a.weight_decay, a.hidden_size,
                 a.context_hidden, a.fusion_hidden, a.station_embedding_dim, a.dropout,
                 a.grad_clip, a.seed, not (a.no_s2 or a.salinity_only), not a.salinity_only)
    (a.output_dir / "config.json").write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")
    started = time.time()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    df = pd.read_csv(a.data, parse_dates=["date"]).sort_values(["station_id", "date"]).reset_index(drop=True)
    mapping = {s: i for i, s in enumerate(sorted(df.station_id.unique()))}
    df["station_idx"] = df.station_id.map(mapping).astype("int64")
    requested_dynamic = DYNAMIC_SALINITY + (DYNAMIC_ERA5 if cfg.use_era5 else [])
    dynamic_cols = [c for c in requested_dynamic if c in df]
    context_cols = [c for c in (["lat", "lon"] + (S2_CORE if cfg.use_s2 else [])) if c in df]
    train_end, val_end = pd.Timestamp(a.train_end), pd.Timestamp(a.val_end)
    train_rows = df.date <= train_end
    dynamic_scaler, context_scaler = Standardizer(), Standardizer()
    dynamic_scaler.fit(df[train_rows], dynamic_cols); context_scaler.fit(df[train_rows], context_cols)
    dynamic, context = dynamic_scaler.transform(df), context_scaler.transform(df)
    built = {s: windows(df, dynamic, context, a.lookback, a.horizon, s, train_end, val_end) for s in ("train", "val", "test")}
    residual_mean = float(built["train"][3].mean()); residual_std = float(built["train"][3].std()) or 1.0
    loaders = {}
    for split, (x, c, station, residual, baseline, meta) in built.items():
        residual_scaled = ((residual - residual_mean) / residual_std).astype(np.float32)
        loaders[split] = DataLoader(Samples(x, c, station, residual_scaled, baseline), batch_size=a.batch_size, shuffle=split == "train")
        meta.to_csv(a.output_dir / f"{split}_samples.csv", index=False)
    model = MultiSourceLSTM(len(dynamic_cols), len(context_cols), len(mapping), cfg).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=a.weight_decay)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, factor=0.5, patience=max(3, a.patience // 3))
    criterion = nn.HuberLoss(delta=1.0)
    best_rmse, best_epoch, history = math.inf, 0, []
    for epoch in range(1, a.epochs + 1):
        model.train(); losses = []
        for x, c, station, residual, _ in loaders["train"]:
            optimizer.zero_grad(set_to_none=True)
            pred = model(x.to(device), c.to(device), station.to(device))
            loss = criterion(pred, residual.to(device)); loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), a.grad_clip); optimizer.step(); losses.append(loss.item())
        val_metric, _, _ = evaluate(model, loaders["val"], device, residual_mean, residual_std)
        scheduler.step(val_metric["rmse"])
        history.append({"epoch": epoch, "train_loss": np.mean(losses), **{f"val_{k}": v for k, v in val_metric.items()}})
        print(f"epoch={epoch:03d} train_loss={np.mean(losses):.5f} val_rmse={val_metric['rmse']:.4f} val_mae={val_metric['mae']:.4f} val_r2={val_metric['r2']:.4f}")
        if val_metric["rmse"] < best_rmse:
            best_rmse, best_epoch = val_metric["rmse"], epoch
            metadata = {"dynamic_cols": dynamic_cols, "context_cols": context_cols, "station_mapping": mapping,
                        "dynamic_scaler": dynamic_scaler.export(), "context_scaler": context_scaler.export(),
                        "residual_mean": residual_mean, "residual_std": residual_std}
            torch.save({"model_state_dict": model.state_dict(), "config": asdict(cfg), "metadata": metadata,
                        "best_epoch": epoch, "best_val_rmse": best_rmse}, a.output_dir / "best_model.pt")
            (a.output_dir / "training_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        if epoch - best_epoch >= a.patience:
            print(f"Early stopping at epoch {epoch}; best epoch was {best_epoch}."); break
    pd.DataFrame(history).to_csv(a.output_dir / "training_history.csv", index=False)
    checkpoint = torch.load(a.output_dir / "best_model.pt", map_location=device); model.load_state_dict(checkpoint["model_state_dict"])
    results = {"best_epoch": best_epoch, "best_val_rmse": best_rmse}
    for split in ("val", "test"):
        metric, pred, truth = evaluate(model, loaders[split], device, residual_mean, residual_std)
        out = built[split][5].copy(); out["y_true"] = truth; out["y_pred"] = pred
        out["error"] = out.y_pred - out.y_true; out["abs_error"] = out.error.abs()
        out.to_csv(a.output_dir / f"{split}_predictions.csv", index=False); results[split] = metric
    results["elapsed_seconds"] = time.time() - started
    (a.output_dir / "metrics.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
