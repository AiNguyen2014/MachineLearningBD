"""Run XGBoost for spatial salinity estimation.

The target salinity columns are labels only. By default the feature set excludes
station identity and every salinity-derived input, including lagged salinity.
This makes the experiment suitable for checking whether spatial, seasonal,
weather, and Sentinel-2 variables can generalize to unseen stations.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold

try:
    from xgboost import XGBRegressor
except ImportError as exc:  # pragma: no cover - runtime guidance
    raise SystemExit(
        "Missing xgboost. Install it with:\n"
        "  ./.venv_lstm/bin/python -m pip install xgboost"
    ) from exc


ROOT = Path(__file__).resolve().parent
DEFAULT_DATA = ROOT / "data/weekly_ml_dataset_v2_leftjoin.csv"
DEFAULT_OUT = ROOT / "outputs"


STATIC = [
    "lon_first",
    "lat_first",
    "DEM_first",
    "Distance_to_River_first",
    "Distance_to_Coast_first",
]
WEATHER = [
    "temperature_2m_c_mean",
    "precipitation_mm_sum",
    "rainy_day_sum",
    "potential_evaporation_mm_sum",
    "runoff_mm_sum",
    "runoff_mm_max",
    "wind_speed_10m_ms_mean",
    "wind_speed_10m_ms_max",
    "surface_pressure_hpa_min",
    "soil_moisture_layer1_vol_mean",
    "solar_radiation_mj_m2_sum",
]
SPECTRAL = [
    "MNDWI_median_week",
    "NDWI_median_week",
    "NDVI_median_week",
    "B11_median_week",
    "B12_median_week",
    "Red_SWIR1_median_week",
    "Red_SWIR2_median_week",
    "BGRratio_median_week",
    "NDCI_median_week",
    "s2_available",
]
TARGET_COLS = {
    "salinity_max_max",
    "salinity_max_mean",
    "salinity_max_min",
    "salinity_max_std",
    "sal_p90_raw",
}
IDENTITY_COLS = {"station_id", "station_name_first", "date", "week_date"}


@dataclass
class Config:
    data: str
    output_dir: str
    time_unit: str
    split: str
    target: str
    n_splits: int
    monthly_min_reliable_weeks: int
    salinity_cap: float
    include_completeness: bool
    include_source_format: bool
    include_river: bool
    random_state: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--time-unit", choices=["weekly", "monthly"], default="weekly")
    parser.add_argument(
        "--split",
        choices=["temporal", "spatial-cv", "spatiotemporal-cv"],
        default="spatial-cv",
    )
    parser.add_argument("--target", default="salinity_max_mean")
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--monthly-min-reliable-weeks", type=int, default=2)
    parser.add_argument("--salinity-cap", type=float, default=40.0)
    parser.add_argument("--include-completeness", action="store_true")
    parser.add_argument("--include-source-format", action="store_true")
    parser.add_argument("--include-river", action="store_true")
    parser.add_argument("--random-state", type=int, default=42)
    return parser.parse_args()


def coerce_numeric(df: pd.DataFrame) -> pd.DataFrame:
    keep_str = {
        "station_id",
        "date",
        "station_name_first",
        "river_name_first",
        "source_format",
        "week_date",
    }
    out = df.copy()
    for col in out.columns:
        if col in keep_str or pd.api.types.is_numeric_dtype(out[col]):
            continue
        converted = pd.to_numeric(
            out[col].astype(str).str.replace(",", ".", regex=False),
            errors="coerce",
        )
        if converted.notna().mean() > 0.8:
            out[col] = converted
    return out


def load_data(path: Path, target: str, salinity_cap: float) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["date"])
    df = coerce_numeric(df)
    if target not in df:
        raise ValueError(f"Missing target column: {target}")
    for col in TARGET_COLS:
        if col in df:
            df[col] = df[col].clip(upper=salinity_cap)
    df = df.sort_values(["station_id", "date"]).reset_index(drop=True)
    df["source_format"] = df["source_format"].fillna("unknown")
    return df


def first_non_null(values: pd.Series):
    values = values.dropna()
    return values.iloc[0] if len(values) else np.nan


def mode_or_first(values: pd.Series):
    values = values.dropna()
    if not len(values):
        return "unknown"
    mode = values.mode()
    return mode.iloc[0] if len(mode) else values.iloc[0]


def aggregate_monthly(df: pd.DataFrame, min_reliable_weeks: int) -> pd.DataFrame:
    group_cols = ["station_id", "year", "month"]
    agg = {
        "date": "min",
        "station_name_first": first_non_null,
        "river_name_first": first_non_null,
        "source_format": mode_or_first,
        "lon_first": "first",
        "lat_first": "first",
        "DEM_first": "first",
        "Distance_to_River_first": "first",
        "Distance_to_Coast_first": "first",
        "salinity_max_max": "max",
        "salinity_max_mean": "mean",
        "salinity_max_min": "min",
        "sal_p90_raw": "mean",
        "n_days": "sum",
        "completeness_pct": "mean",
        "s2_available": "max",
        "s2_obs_count": "sum",
    }
    for col in df.columns:
        if col in agg or col in group_cols or col in {"week", "day_of_year", "week_date", "mean_reliable"}:
            continue
        if col.endswith("_sum"):
            agg[col] = "sum"
        elif col.endswith("_max"):
            agg[col] = "max"
        elif col.endswith("_min"):
            agg[col] = "min"
        elif col.endswith("_mean") or col.endswith("_std"):
            agg[col] = "mean"
        elif col.endswith("_median_week") or col.startswith("s2_"):
            agg[col] = "median"

    monthly = df.groupby(group_cols, as_index=False).agg(agg)
    reliable_counts = (
        df[df["mean_reliable"].eq(True)]
        .groupby(group_cols)
        .size()
        .rename("n_reliable_weeks")
        .reset_index()
    )
    total_counts = df.groupby(group_cols).size().rename("n_weeks").reset_index()
    monthly = monthly.merge(total_counts, on=group_cols, how="left")
    monthly = monthly.merge(reliable_counts, on=group_cols, how="left")
    monthly["n_reliable_weeks"] = monthly["n_reliable_weeks"].fillna(0).astype(int)
    monthly["mean_reliable"] = monthly["n_reliable_weeks"] >= min_reliable_weeks
    monthly["date"] = pd.to_datetime(monthly["date"])
    monthly["day_of_year"] = monthly["date"].dt.dayofyear
    monthly["week"] = monthly["date"].dt.isocalendar().week.astype(int)
    monthly["source_format"] = monthly["source_format"].fillna("unknown")
    return monthly.sort_values(["station_id", "date"]).reset_index(drop=True)


def add_features(df: pd.DataFrame, include_source_format: bool, include_river: bool) -> pd.DataFrame:
    out = df.copy()
    doy = out["day_of_year"]
    out["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    out["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    out["week_sin"] = np.sin(2 * np.pi * out["week"] / 52)
    out["week_cos"] = np.cos(2 * np.pi * out["week"] / 52)
    out["month_sin"] = np.sin(2 * np.pi * out["month"] / 12)
    out["month_cos"] = np.cos(2 * np.pi * out["month"] / 12)
    if include_source_format:
        out = pd.concat([out, pd.get_dummies(out["source_format"], prefix="sf")], axis=1)
    if include_river:
        river = out["river_name_first"].fillna("unknown")
        out = pd.concat([out, pd.get_dummies(river, prefix="river")], axis=1)
    return out


def feature_columns(
    df: pd.DataFrame,
    include_completeness: bool,
    include_source_format: bool,
    include_river: bool,
) -> list[str]:
    season = ["doy_sin", "doy_cos", "week_sin", "week_cos", "month_sin", "month_cos"]
    quality = ["s2_available"]
    if include_completeness:
        quality.append("completeness_pct")
    if include_source_format:
        quality.extend([c for c in df.columns if c.startswith("sf_")])
    if include_river:
        quality.extend([c for c in df.columns if c.startswith("river_")])
    raw = STATIC + season + WEATHER + SPECTRAL + quality
    blocked = TARGET_COLS | IDENTITY_COLS | {"year", "month", "week", "day_of_year"}
    cols = []
    for col in raw:
        if col in df.columns and col not in blocked and col not in cols:
            cols.append(col)
    salinity_leaks = [c for c in cols if "salinity" in c.lower()]
    if salinity_leaks:
        raise ValueError(f"Salinity-derived features are not allowed: {salinity_leaks}")
    return cols


def reliable_mask(df: pd.DataFrame, target: str) -> pd.Series:
    return df["mean_reliable"].eq(True) & df[target].notna()


def model(random_state: int) -> XGBRegressor:
    return XGBRegressor(
        objective="reg:squarederror",
        learning_rate=0.03,
        max_depth=4,
        n_estimators=2500,
        early_stopping_rounds=60,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=random_state,
        missing=np.nan,
    )


def metrics(y_true_log: np.ndarray, y_pred_log: np.ndarray) -> dict[str, float]:
    y_true = np.expm1(y_true_log)
    y_pred = np.expm1(y_pred_log)
    return {
        "n": int(len(y_true)),
        "r2_log": float(r2_score(y_true_log, y_pred_log)) if len(y_true) > 1 else math.nan,
        "rmse_gl": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "mae_gl": float(mean_absolute_error(y_true, y_pred)),
        "bias_gl": float(np.mean(y_pred - y_true)),
    }


def fit_predict(
    df: pd.DataFrame,
    features: list[str],
    target: str,
    train_mask: pd.Series,
    val_mask: pd.Series,
    test_mask: pd.Series,
    random_state: int,
) -> tuple[dict[str, float], pd.DataFrame, pd.DataFrame]:
    y = np.log1p(df[target])
    reg = model(random_state)
    eval_set = [(df.loc[val_mask, features], y[val_mask])] if val_mask.sum() else None
    reg.fit(
        df.loc[train_mask, features],
        y[train_mask],
        eval_set=eval_set,
        verbose=False,
    )
    pred_log = reg.predict(df.loc[test_mask, features])
    metric = metrics(y[test_mask].to_numpy(), pred_log)
    pred = df.loc[test_mask, ["station_id", "date", "year", "source_format", target]].copy()
    pred["y_true"] = np.expm1(y[test_mask].to_numpy())
    pred["y_pred"] = np.expm1(pred_log)
    pred["error"] = pred["y_pred"] - pred["y_true"]
    pred["abs_error"] = pred["error"].abs()
    imp = pd.DataFrame({"feature": features, "importance": reg.feature_importances_})
    return metric, pred, imp


def temporal_split(df: pd.DataFrame, rel: pd.Series) -> list[tuple[str, pd.Series, pd.Series, pd.Series, list[str]]]:
    train = rel & df["year"].isin([2020, 2021])
    val = rel & df["year"].eq(2022)
    test = rel & df["year"].eq(2023)
    return [("temporal", train, val, test, sorted(df.loc[test, "station_id"].unique()))]


def spatial_cv_splits(
    df: pd.DataFrame,
    rel: pd.Series,
    n_splits: int,
    spatiotemporal: bool,
) -> list[tuple[str, pd.Series, pd.Series, pd.Series, list[str]]]:
    stations = df.loc[rel, "station_id"]
    splitter = GroupKFold(n_splits=n_splits)
    out = []
    dummy_x = np.zeros((rel.sum(), 1))
    rel_idx = df.index[rel].to_numpy()
    for fold, (train_pos, test_pos) in enumerate(splitter.split(dummy_x, groups=stations), start=1):
        train_stations = set(df.loc[rel_idx[train_pos], "station_id"])
        test_stations = set(df.loc[rel_idx[test_pos], "station_id"])
        if spatiotemporal:
            train = rel & df["station_id"].isin(train_stations) & df["year"].isin([2020, 2021])
            val = rel & df["station_id"].isin(train_stations) & df["year"].eq(2022)
            test = rel & df["station_id"].isin(test_stations) & df["year"].eq(2023)
        else:
            train = rel & df["station_id"].isin(train_stations) & ~df["year"].eq(2022)
            val = rel & df["station_id"].isin(train_stations) & df["year"].eq(2022)
            test = rel & df["station_id"].isin(test_stations)
        if train.sum() and val.sum() and test.sum():
            out.append((f"fold_{fold}", train, val, test, sorted(test_stations)))
    return out


def main() -> None:
    args = parse_args()
    started = time.strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_root / f"{args.split}_{started}"
    output_dir.mkdir(parents=True, exist_ok=True)
    cfg = Config(
        data=str(args.data),
        output_dir=str(output_dir),
        time_unit=args.time_unit,
        split=args.split,
        target=args.target,
        n_splits=args.n_splits,
        monthly_min_reliable_weeks=args.monthly_min_reliable_weeks,
        salinity_cap=args.salinity_cap,
        include_completeness=args.include_completeness,
        include_source_format=args.include_source_format,
        include_river=args.include_river,
        random_state=args.random_state,
    )
    (output_dir / "config.json").write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")

    df = load_data(args.data, args.target, args.salinity_cap)
    if args.time_unit == "monthly":
        df = aggregate_monthly(df, args.monthly_min_reliable_weeks)
    df = add_features(df, args.include_source_format, args.include_river)
    features = feature_columns(
        df,
        args.include_completeness,
        args.include_source_format,
        args.include_river,
    )
    (output_dir / "feature_columns.txt").write_text("\n".join(features) + "\n", encoding="utf-8")
    rel = reliable_mask(df, args.target)

    if args.split == "temporal":
        splits = temporal_split(df, rel)
    elif args.split == "spatial-cv":
        splits = spatial_cv_splits(df, rel, args.n_splits, spatiotemporal=False)
    else:
        splits = spatial_cv_splits(df, rel, args.n_splits, spatiotemporal=True)
    if not splits:
        raise ValueError("No valid split was created. Check n_splits and data coverage.")

    metric_rows = []
    prediction_frames = []
    importance_frames = []
    for name, train, val, test, holdout_stations in splits:
        metric, pred, imp = fit_predict(
            df,
            features,
            args.target,
            train,
            val,
            test,
            args.random_state,
        )
        metric_rows.append({
            "split": name,
            "n_train": int(train.sum()),
            "n_val": int(val.sum()),
            "n_test": int(test.sum()),
            "n_holdout_stations": len(holdout_stations),
            "holdout_stations": ",".join(holdout_stations),
            **metric,
        })
        pred["split"] = name
        prediction_frames.append(pred)
        imp["split"] = name
        importance_frames.append(imp)

    metrics_df = pd.DataFrame(metric_rows)
    metrics_df.to_csv(output_dir / "metrics.csv", index=False)
    pd.concat(prediction_frames, ignore_index=True).to_csv(output_dir / "predictions.csv", index=False)
    importance = pd.concat(importance_frames, ignore_index=True)
    importance.to_csv(output_dir / "feature_importance_by_split.csv", index=False)
    (
        importance.groupby("feature", as_index=False)["importance"]
        .mean()
        .sort_values("importance", ascending=False)
        .to_csv(output_dir / "feature_importance.csv", index=False)
    )
    summary = metrics_df[["r2_log", "rmse_gl", "mae_gl", "bias_gl"]].mean(numeric_only=True)
    print(f"Output: {output_dir}")
    print(metrics_df.to_string(index=False))
    print("\nMean metrics:")
    print(summary.to_string())


if __name__ == "__main__":
    main()
