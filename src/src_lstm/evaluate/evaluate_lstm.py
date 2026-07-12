"""Create reproducible LSTM tuning tables and the final Vietnamese model report."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
TUNING = ROOT / "models/lstm_tuning"
FINAL_RUNS = [
    TUNING / "c05_sal_h128",
    TUNING / "c05_sal_h128_s07",
    TUNING / "c05_sal_h128_s123",
]
OUT = ROOT / "models/lstm_final"


def metrics(y_true: pd.Series, y_pred: pd.Series) -> dict[str, float | int]:
    error = y_pred.to_numpy() - y_true.to_numpy()
    denominator = np.sum((y_true.to_numpy() - y_true.mean()) ** 2)
    return {
        "n": len(y_true),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "mae": float(np.mean(np.abs(error))),
        "bias": float(np.mean(error)),
        "r2": float(1 - np.sum(error**2) / denominator) if denominator else math.nan,
    }


def collect_trials() -> pd.DataFrame:
    rows = []
    for metric_path in sorted(TUNING.glob("*/metrics.json")):
        run_dir = metric_path.parent
        metric = json.loads(metric_path.read_text(encoding="utf-8"))
        config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
        rows.append({
            "trial": run_dir.name,
            "feature_set": config["feature_set"],
            "horizon": config["horizon"],
            "lookback": config["lookback"],
            "hidden_size": config["hidden_size"],
            "num_layers": config["num_layers"],
            "dropout": config["dropout"],
            "loss": config.get("loss", "huber"),
            "seed": config["seed"],
            "best_epoch": metric["best_epoch"],
            "n_features": metric.get("n_features"),
            "val_rmse": metric["val"]["rmse"],
            "val_mae": metric["val"]["mae"],
            "val_r2": metric["val"]["r2"],
            "test_rmse": metric["test"]["rmse"],
            "test_mae": metric["test"]["mae"],
            "test_r2": metric["test"]["r2"],
            "elapsed_seconds": metric.get("elapsed_seconds"),
        })
    return pd.DataFrame(rows).sort_values(["horizon", "val_rmse"])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    trials = collect_trials()
    trials.to_csv(OUT / "tuning_results_all.csv", index=False)

    seed_rows = []
    prediction_frames = []
    for run in FINAL_RUNS:
        config = json.loads((run / "config.json").read_text(encoding="utf-8"))
        metric = json.loads((run / "metrics.json").read_text(encoding="utf-8"))
        seed_rows.append({"seed": config["seed"], **metric["val"], **{f"test_{k}": v for k, v in metric["test"].items()}})
        pred = pd.read_csv(run / "test_predictions.csv")
        prediction_frames.append(pred[["station_id", "target_date", "input_end", "y_true", "y_pred"]].rename(columns={"y_pred": f"pred_seed_{config['seed']}"}))

    seeds = pd.DataFrame(seed_rows).sort_values("seed")
    seeds.to_csv(OUT / "final_architecture_seed_results.csv", index=False)
    ensemble = prediction_frames[0]
    for frame in prediction_frames[1:]:
        ensemble = ensemble.merge(frame.drop(columns=["input_end", "y_true"]), on=["station_id", "target_date"], validate="one_to_one")
    pred_cols = [c for c in ensemble if c.startswith("pred_seed_")]
    ensemble["y_pred"] = ensemble[pred_cols].mean(axis=1)
    ensemble["error"] = ensemble["y_pred"] - ensemble["y_true"]
    ensemble.to_csv(OUT / "test_predictions_ensemble.csv", index=False)

    overall = pd.DataFrame([{"model": "LSTM ensemble (3 seeds)", **metrics(ensemble.y_true, ensemble.y_pred)}])
    daily = pd.read_csv(ROOT / "Data/processed/lstm_daily_multisource_2020_2023.csv", parse_dates=["date"])
    baseline = ensemble.copy()
    baseline["input_end"] = pd.to_datetime(baseline["input_end"])
    baseline = baseline.merge(
        daily[["station_id", "date", "salinity_input"]],
        left_on=["station_id", "input_end"], right_on=["station_id", "date"],
    ).dropna(subset=["salinity_input"])
    comparable_lstm = metrics(baseline.y_true, baseline.y_pred)
    persistence = metrics(baseline.y_true, baseline.salinity_input)
    comparison = pd.DataFrame([
        {"model": "LSTM ensemble", **comparable_lstm},
        {"model": "Persistence t-1", **persistence},
    ])
    comparison.to_csv(OUT / "baseline_comparison.csv", index=False)
    overall.to_csv(OUT / "overall_test_metrics.csv", index=False)

    station_rows = []
    for station, group in ensemble.groupby("station_id"):
        station_rows.append({"station_id": station, **metrics(group.y_true, group.y_pred)})
    station_metrics = pd.DataFrame(station_rows).sort_values("rmse")
    station_metrics.to_csv(OUT / "test_metrics_by_station.csv", index=False)

    ensemble["month"] = pd.to_datetime(ensemble["target_date"]).dt.to_period("M").astype(str)
    month_rows = [{"month": month, **metrics(g.y_true, g.y_pred)} for month, g in ensemble.groupby("month")]
    pd.DataFrame(month_rows).to_csv(OUT / "test_metrics_by_month.csv", index=False)

    mean_test = seeds["test_rmse"].mean()
    std_test = seeds["test_rmse"].std(ddof=1)
    ens = overall.iloc[0]
    best_station = station_metrics.iloc[0]
    worst_station = station_metrics.iloc[-1]
    report = f"""# Báo cáo mô hình LSTM dự báo độ mặn theo ngày

## Thiết kế thí nghiệm

- Dữ liệu: 22 trạm, giai đoạn 2020-2023; target là độ mặn cực đại quan trắc.
- Chia theo thời gian: train đến 31/12/2021, validation năm 2022, test năm 2023.
- Bài toán chính: dự báo trước 1 ngày từ cửa sổ 30 ngày; scaler và median imputer chỉ fit trên train.
- Chọn mô hình hoàn toàn theo RMSE validation. Test 2023 không được dùng để chọn siêu tham số.
- Cấu hình cuối: nhóm biến `salinity`, LSTM 1 tầng, 128 hidden units, dropout 0.15, Huber loss, station embedding 8 chiều.

## Kết quả chính

Ba seed độc lập cho test RMSE trung bình **{mean_test:.3f} ± {std_test:.3f}**. Ensemble trung bình ba seed đạt RMSE **{ens.rmse:.3f}**, MAE **{ens.mae:.3f}**, R² **{ens.r2:.3f}** trên {int(ens.n):,} mẫu test năm 2023.

Theo trạm, RMSE tốt nhất là **{best_station.station_id} ({best_station.rmse:.3f})** và cao nhất là **{worst_station.station_id} ({worst_station.rmse:.3f})**. Chi tiết nằm trong `test_metrics_by_station.csv` và `test_metrics_by_month.csv`.

## Ablation và tuning

Thử nghiệm ablation cho thấy nhóm biến chỉ gồm lịch sử mặn, trạng thái quan trắc, tọa độ và mùa vụ cho kết quả validation tốt nhất. Việc thêm ERA5 hoặc Sentinel-2 theo tháng không cải thiện RMSE trong thiết lập dự báo ngày kế tiếp. Kết quả này hợp lý với tính tự tương quan mạnh của độ mặn ngày và độ phân giải thời gian thấp hơn của composite Sentinel-2. Toàn bộ cấu hình và metric được lưu trong `tuning_results_all.csv`.

## Baseline bắt buộc phải báo cáo

Trên {int(persistence['n']):,} mẫu có giá trị mặn đầu vào ở ngày liền trước, persistence baseline đạt RMSE **{persistence['rmse']:.3f}**, trong khi LSTM ensemble đạt **{comparable_lstm['rmse']:.3f}** trên đúng tập mẫu đó. Như vậy LSTM hiện chưa vượt baseline persistence cho dự báo 1 ngày. R² cao của LSTM vẫn đúng, nhưng chưa đủ để khẳng định lợi ích dự báo so với quy tắc đơn giản.

## Diễn giải và giới hạn

Kết quả phù hợp để trình bày như một baseline LSTM mạnh và một kết quả ablation trung thực, nhưng chưa nên tuyên bố mô hình cuối có ưu thế vận hành ở horizon 1 ngày. Các hướng tiếp theo nên ưu tiên dự báo 3/7 ngày, residual forecasting so với persistence, và đánh giá trên 2025. ERA5/Sentinel-2 có thể hữu ích hơn ở horizon dài hoặc trong bài toán ước lượng không gian, dù chưa giúp thiết lập LSTM hiện tại.

## External test 2025

Raw 2025 hiện có 8/22 trạm: BinhDai, AnThuan, BenTrai, LocThuan, TraVinh, CauNoi, TanAn và BenLuc. Có thể dùng làm external temporal test trên tập trạm giao nhau. Phải giữ nguyên preprocessing, scaler, feature set và checkpoint; không tune theo 2025. Vì cấu hình cuối chỉ dùng nhóm biến mặn, không bắt buộc lấy ERA5/Sentinel-2 2025 cho phép thử này.

## Tái lập

Chạy `python tune_lstm.py` để tái lập search ban đầu và `python evaluate_lstm.py` để tạo lại các bảng báo cáo. Mỗi trial lưu config, seed, lịch sử epoch, checkpoint, prediction và metric trong thư mục riêng.
"""
    (OUT / "model_report_vi.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
