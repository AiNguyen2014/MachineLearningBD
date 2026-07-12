"""Summarize Persistence, LSTM-S, MS-only, and the proposed MS-LSTM."""

from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[3]
TUNE = REPO_ROOT / "models/lstm/ms_lstm_tuning"
OUT = REPO_ROOT / "models/lstm/ms_lstm_final"
TARGET_HORIZON = 7
FULL_RUNS = [TUNE / "h07_full_h128", TUNE / "h07_full_h128_s07", TUNE / "h07_full_h128_s123"]
SALINITY_RUN = TUNE / "h07_salinity_only"
MS_ONLY_RUN = TUNE / "h07_ms_only"


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
        if c["horizon"] != TARGET_HORIZON:
            continue
        trial_rows.append({"trial": path.parent.name, "use_era5": c.get("use_era5", True), "use_s2": c["use_s2"],
                           "use_salinity_history": c.get("use_salinity_history", True),
                           "prediction_mode": c.get("prediction_mode", "residual"),
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
    sal = sal[["station_id", "target_date", "y_true", "y_pred"]]
    sal = merged[["station_id", "target_date"]].merge(sal, on=["station_id", "target_date"], validate="one_to_one")
    comparison_rows = [
        {"model": "Persistence", "data_sources": "Recent salinity", **score(merged.y_true, merged.baseline)},
        {"model": "LSTM-S", "data_sources": "Salinity history", **score(sal.y_true, sal.y_pred)},
    ]
    ms_only = None
    if (MS_ONLY_RUN / "test_predictions.csv").exists():
        ms_only = pd.read_csv(MS_ONLY_RUN / "test_predictions.csv")
        ms_only = ms_only[["station_id", "target_date", "y_true", "y_pred"]]
        ms_only = merged[["station_id", "target_date"]].merge(ms_only, on=["station_id", "target_date"], validate="one_to_one")
        comparison_rows.append({"model": "MS-only", "data_sources": "ERA5-Land + Sentinel-2 + context", **score(ms_only.y_true, ms_only.y_pred)})
    comparison_rows.append({"model": "MS-LSTM ensemble", "data_sources": "Salinity + ERA5-Land + Sentinel-2", **score(merged.y_true, merged.ms_lstm_ensemble)})
    comparison = pd.DataFrame(comparison_rows)
    comparison.to_csv(OUT / "four_model_comparison.csv", index=False)
    comparison[comparison.model != "MS-only"].to_csv(OUT / "three_model_comparison.csv", index=False)

    stations = []
    for station, g in merged.groupby("station_id"):
        stations.append({"station_id": station, **score(g.y_true, g.ms_lstm_ensemble)})
    pd.DataFrame(stations).sort_values("rmse").to_csv(OUT / "ms_lstm_metrics_by_station.csv", index=False)

    chosen = min(FULL_RUNS, key=lambda run: json.loads((run / "metrics.json").read_text())["val"]["rmse"])
    for source, target in [("best_model.pt", "best_ms_lstm_selected_by_validation.pt"),
                           ("config.json", "selected_config.json"),
                           ("training_metadata.json", "selected_training_metadata.json"),
                           ("training_history.csv", "selected_training_history.csv")]:
        shutil.copy2(chosen / source, OUT / target)

    base = comparison.loc[comparison.model == "Persistence"].iloc[0]
    lstm_s = comparison.loc[comparison.model == "LSTM-S"].iloc[0]
    ms = comparison.loc[comparison.model == "MS-LSTM ensemble"].iloc[0]
    ms_only_row = comparison.loc[comparison.model == "MS-only"].iloc[0] if "MS-only" in set(comparison.model) else None
    ms_only_table_row = (
        f"| MS-only | {ms_only_row.rmse:.3f} | {ms_only_row.mae:.3f} | {ms_only_row.r2:.3f} |\n"
        if ms_only_row is not None else ""
    )
    ms_only_note = (
        f"MS-only không dùng giá trị mặn lịch sử, chỉ dùng ERA5-Land, Sentinel-2, tọa độ, mùa vụ và station embedding; trên cùng tập test so sánh, mô hình đạt RMSE **{ms_only_row.rmse:.3f}**, MAE **{ms_only_row.mae:.3f}**, R² **{ms_only_row.r2:.3f}**.\n\n"
        if ms_only_row is not None else
        "MS-only đã được hỗ trợ trong code qua `--ms-only`, nhưng chưa có run `a04_ms_only` trong thư mục tuning nên chưa được đưa vào bảng kết quả.\n\n"
    )
    report = f"""# Báo cáo mô hình đa nguồn MS-LSTM

## Các mô hình so sánh

1. **Persistence:** dự báo bằng giá trị mặn gần nhất trong cửa sổ đầu vào.
2. **LSTM-S:** LSTM residual chỉ dùng lịch sử mặn, trạng thái quan trắc và mùa vụ.
3. **MS-only:** mô hình đa nguồn không dùng lịch sử mặn; đầu vào gồm ERA5-Land, Sentinel-2, tọa độ, mùa vụ và định danh trạm.
4. **MS-LSTM:** mô hình đề xuất dùng mặn + ERA5-Land hằng ngày + Sentinel-2 composite tháng trước.

Persistence không cần huấn luyện. LSTM-S, MS-only và MS-LSTM có checkpoint riêng; MS-LSTM là mô hình chính phù hợp với hướng đa nguồn của đề tài.

## Kiến trúc MS-LSTM

- Cửa sổ đầu vào 30 ngày, dự báo trước 7 ngày.
- Nhánh động: 7 biến mặn/trạng thái/mùa vụ và 13 biến ERA5-Land được mã hóa bằng LSTM 1 tầng, 128 hidden units.
- Nhánh ngữ cảnh: tọa độ và 10 biến Sentinel-2 chọn lọc được mã hóa bằng MLP 32 units.
- Station embedding 8 chiều; fusion head 64 units; dropout 0.15.
- Mô hình dự báo residual so với giá trị mặn gần nhất, dùng Huber loss và AdamW.
- Train 2020-2021, validation 2022, test 2023. Chọn kiến trúc và seed theo validation RMSE.

## Kết quả test 2023 cho horizon 7 ngày

| Mô hình | RMSE | MAE | R² |
|---|---:|---:|---:|
| Persistence | {base.rmse:.3f} | {base.mae:.3f} | {base.r2:.3f} |
| LSTM-S | {lstm_s.rmse:.3f} | {lstm_s.mae:.3f} | {lstm_s.r2:.3f} |
{ms_only_table_row}\
| MS-LSTM ensemble | {ms.rmse:.3f} | {ms.mae:.3f} | {ms.r2:.3f} |

MS-LSTM ba seed có test RMSE trung bình **{seeds.test_rmse.mean():.3f} ± {seeds.test_rmse.std(ddof=1):.3f}**. Ensemble dùng trung bình dự đoán của ba seed.

{ms_only_note}

## Ablation nguồn dữ liệu

Trên validation 2022, các cấu hình horizon 7 ngày được so sánh để kiểm tra mức độ đóng góp của từng nguồn dữ liệu. MS-only là thí nghiệm bổ sung để kiểm tra mức độ dữ liệu ngoại sinh có thể giải thích độ mặn khi không có mặn lịch sử. Điều này giúp tách hai câu hỏi: giá trị mặn quá khứ mạnh đến đâu, và dữ liệu khí tượng - viễn thám tự thân đóng góp bao nhiêu. Trên test 2023, cần diễn giải đồng thời Persistence, LSTM-S, MS-only và MS-LSTM để tránh chỉ dựa vào R².

## Cách báo cáo trong paper

MS-LSTM nên được trình bày là mô hình đa nguồn đề xuất; LSTM-S và MS-only là ablation, Persistence là baseline. Không nên chỉ dựa vào R²: cần báo cáo cả RMSE, MAE, kết quả theo trạm, nhiều seed và external test. Toàn bộ trial nằm trong `tuning_results.csv`.
"""
    (OUT / "model_report_vi.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
