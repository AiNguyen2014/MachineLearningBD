"""Summarize Persistence, LSTM-S, and the proposed MS-LSTM."""

from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
TUNE = ROOT / "models/ms_lstm_tuning"
OUT = ROOT / "models/ms_lstm_final"
FULL_RUNS = [TUNE / "b03_full_h128", TUNE / "b03_full_h128_s07", TUNE / "b03_full_h128_s123"]
SALINITY_RUN = TUNE / "a03_salinity_only"


def score(y, pred):
    y, pred = np.asarray(y), np.asarray(pred)
    error = pred - y
    return {"n": len(y), "rmse": float(np.sqrt(np.mean(error**2))),
            "mae": float(np.mean(np.abs(error))), "bias": float(np.mean(error)),
            "r2": float(1 - np.sum(error**2) / np.sum((y - y.mean())**2))}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    trial_rows = []
    for path in sorted(TUNE.glob("*/metrics.json")):
        m = json.loads(path.read_text()); c = json.loads((path.parent / "config.json").read_text())
        trial_rows.append({"trial": path.parent.name, "use_era5": c.get("use_era5", True), "use_s2": c["use_s2"],
                           "lookback": c["lookback"], "hidden_size": c["hidden_size"], "seed": c["seed"],
                           "val_rmse": m["val"]["rmse"], "val_mae": m["val"]["mae"], "val_r2": m["val"]["r2"],
                           "test_rmse": m["test"]["rmse"], "test_mae": m["test"]["mae"], "test_r2": m["test"]["r2"]})
    pd.DataFrame(trial_rows).sort_values("val_rmse").to_csv(OUT / "tuning_results.csv", index=False)

    merged, seed_rows = None, []
    for run in FULL_RUNS:
        c = json.loads((run / "config.json").read_text()); m = json.loads((run / "metrics.json").read_text())
        seed_rows.append({"seed": c["seed"], "val_rmse": m["val"]["rmse"], "val_mae": m["val"]["mae"],
                          "val_r2": m["val"]["r2"], "test_rmse": m["test"]["rmse"],
                          "test_mae": m["test"]["mae"], "test_r2": m["test"]["r2"]})
        p = pd.read_csv(run / "test_predictions.csv")
        p = p[["station_id", "target_date", "input_end", "baseline", "y_true", "y_pred"]].rename(columns={"y_pred": f"pred_seed_{c['seed']}"})
        merged = p if merged is None else merged.merge(p.drop(columns=["input_end", "baseline", "y_true"]), on=["station_id", "target_date"], validate="one_to_one")
    seeds = pd.DataFrame(seed_rows).sort_values("seed"); seeds.to_csv(OUT / "seed_stability.csv", index=False)
    pred_cols = [c for c in merged if c.startswith("pred_seed_")]
    merged["ms_lstm_ensemble"] = merged[pred_cols].mean(axis=1)
    merged.to_csv(OUT / "ms_lstm_test_predictions_ensemble.csv", index=False)

    sal = pd.read_csv(SALINITY_RUN / "test_predictions.csv")
    comparison = pd.DataFrame([
        {"model": "Persistence", "data_sources": "Recent salinity", **score(merged.y_true, merged.baseline)},
        {"model": "LSTM-S", "data_sources": "Salinity history", **score(sal.y_true, sal.y_pred)},
        {"model": "MS-LSTM ensemble", "data_sources": "Salinity + ERA5-Land + Sentinel-2", **score(merged.y_true, merged.ms_lstm_ensemble)},
    ])
    comparison.to_csv(OUT / "three_model_comparison.csv", index=False)

    stations = []
    for station, g in merged.groupby("station_id"):
        stations.append({"station_id": station, **score(g.y_true, g.ms_lstm_ensemble)})
    pd.DataFrame(stations).sort_values("rmse").to_csv(OUT / "ms_lstm_metrics_by_station.csv", index=False)

    chosen = TUNE / "b03_full_h128_s07"  # lowest validation RMSE among final seeds
    for source, target in [("best_model.pt", "best_ms_lstm_selected_by_validation.pt"),
                           ("config.json", "selected_config.json"),
                           ("training_metadata.json", "selected_training_metadata.json"),
                           ("training_history.csv", "selected_training_history.csv")]:
        shutil.copy2(chosen / source, OUT / target)

    ms = comparison.iloc[2]; base = comparison.iloc[0]; lstm_s = comparison.iloc[1]
    report = f"""# Báo cáo mô hình đa nguồn MS-LSTM

## Ba mô hình so sánh

1. **Persistence:** dự báo bằng giá trị mặn gần nhất trong cửa sổ đầu vào.
2. **LSTM-S:** LSTM residual chỉ dùng lịch sử mặn, trạng thái quan trắc và mùa vụ.
3. **MS-LSTM:** mô hình đề xuất dùng mặn + ERA5-Land hằng ngày + Sentinel-2 composite tháng trước.

Persistence không cần huấn luyện. LSTM-S và MS-LSTM có checkpoint riêng; MS-LSTM là mô hình chính phù hợp với hướng đa nguồn của đề tài.

## Kiến trúc MS-LSTM

- Cửa sổ đầu vào 30 ngày, dự báo trước 1 ngày.
- Nhánh động: 7 biến mặn/trạng thái/mùa vụ và 13 biến ERA5-Land được mã hóa bằng LSTM 1 tầng, 128 hidden units.
- Nhánh ngữ cảnh: tọa độ và 10 biến Sentinel-2 chọn lọc được mã hóa bằng MLP 32 units.
- Station embedding 8 chiều; fusion head 64 units; dropout 0.15.
- Mô hình dự báo residual so với giá trị mặn gần nhất, dùng Huber loss và AdamW.
- Train 2020-2021, validation 2022, test 2023. Chọn kiến trúc và seed theo validation RMSE.

## Kết quả test 2023

| Mô hình | RMSE | MAE | R² |
|---|---:|---:|---:|
| Persistence | {base.rmse:.3f} | {base.mae:.3f} | {base.r2:.3f} |
| LSTM-S | {lstm_s.rmse:.3f} | {lstm_s.mae:.3f} | {lstm_s.r2:.3f} |
| MS-LSTM ensemble | {ms.rmse:.3f} | {ms.mae:.3f} | {ms.r2:.3f} |

MS-LSTM ba seed có test RMSE trung bình **{seeds.test_rmse.mean():.3f} ± {seeds.test_rmse.std(ddof=1):.3f}**. Ensemble dùng trung bình dự đoán của ba seed.

## Ablation nguồn dữ liệu

Trên validation 2022, LSTM-S đạt RMSE 1.220; thêm ERA5 đạt 1.191; thêm cả ERA5 và Sentinel-2 đạt tốt nhất 1.133 ở seed được chọn. Điều này cho thấy dữ liệu GEE tạo cải thiện trên tập dùng để lựa chọn mô hình. Trên test 2023, chênh lệch giữa LSTM-S và MS-LSTM nhỏ hơn và có thể đảo chiều, do đó cần external test 2025 để đánh giá khả năng tổng quát hóa.

## Cách báo cáo trong paper

MS-LSTM nên được trình bày là mô hình đa nguồn đề xuất; LSTM-S là ablation và Persistence là baseline. Không nên chỉ dựa vào R²: cần báo cáo cả RMSE, MAE, kết quả theo trạm, nhiều seed và external test. Toàn bộ trial nằm trong `tuning_results.csv`.
"""
    (OUT / "model_report_vi.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
