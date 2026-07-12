"""Run a small, reproducible LSTM search and rank trials by validation RMSE."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "models/lstm_tuning")
    parser.add_argument("--epochs", type=int, default=70)
    parser.add_argument("--patience", type=int, default=10)
    return parser.parse_args()


TRIALS = [
    # Ablation first: isolate the contribution of each data source.
    {"name": "a01_salinity_l30", "feature_set": "salinity", "lookback": 30, "hidden": 64, "layers": 1, "dropout": 0.10},
    {"name": "a02_weather_l30", "feature_set": "weather", "lookback": 30, "hidden": 64, "layers": 1, "dropout": 0.10},
    {"name": "a03_multi_compact_l30", "feature_set": "multisource_compact", "lookback": 30, "hidden": 64, "layers": 1, "dropout": 0.10},
    {"name": "a04_multi_full_l30", "feature_set": "multisource", "lookback": 30, "hidden": 64, "layers": 1, "dropout": 0.10},
    # Temporal/model capacity alternatives for the strongest practical feature set.
    {"name": "b01_multi_l14", "feature_set": "multisource_compact", "lookback": 14, "hidden": 64, "layers": 1, "dropout": 0.10},
    {"name": "b02_multi_l60", "feature_set": "multisource_compact", "lookback": 60, "hidden": 64, "layers": 1, "dropout": 0.10},
    {"name": "b03_multi_h128", "feature_set": "multisource_compact", "lookback": 30, "hidden": 128, "layers": 1, "dropout": 0.15},
    {"name": "b04_multi_2layer", "feature_set": "multisource_compact", "lookback": 30, "hidden": 96, "layers": 2, "dropout": 0.20},
]


def main() -> None:
    args = parse_args()
    args.output_root.mkdir(parents=True, exist_ok=True)
    rows = []
    for trial in TRIALS:
        output_dir = args.output_root / trial["name"]
        cmd = [
            sys.executable, str(ROOT / "train_lstm.py"),
            "--output-dir", str(output_dir),
            "--feature-set", trial["feature_set"],
            "--lookback", str(trial["lookback"]),
            "--hidden-size", str(trial["hidden"]),
            "--num-layers", str(trial["layers"]),
            "--dropout", str(trial["dropout"]),
            "--epochs", str(args.epochs),
            "--patience", str(args.patience),
        ]
        print(f"\n=== {trial['name']} ===", flush=True)
        subprocess.run(cmd, check=True)
        metrics = json.loads((output_dir / "metrics.json").read_text(encoding="utf-8"))
        rows.append({
            **trial,
            "best_epoch": metrics["best_epoch"],
            "val_rmse": metrics["val"]["rmse"],
            "val_mae": metrics["val"]["mae"],
            "val_r2": metrics["val"]["r2"],
            "test_rmse_diagnostic": metrics["test"]["rmse"],
            "elapsed_seconds": metrics["elapsed_seconds"],
            "n_features": metrics["n_features"],
        })
        with (args.output_root / "tuning_results.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(sorted(rows, key=lambda row: row["val_rmse"]))

    best = min(rows, key=lambda row: row["val_rmse"])
    (args.output_root / "best_trial.json").write_text(
        json.dumps(best, indent=2), encoding="utf-8"
    )
    print(f"\nBest by validation RMSE: {best['name']} ({best['val_rmse']:.4f})")


if __name__ == "__main__":
    main()
