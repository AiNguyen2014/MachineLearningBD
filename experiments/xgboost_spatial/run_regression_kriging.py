"""Spatial salinity baselines and regression-kriging-style interpolation.

The drift model is Ridge regression on map-ready covariates. Salinity is never
used as a drift feature. For spatial mapping, residuals from observed stations
at the target date are interpolated to a held-out station with IDW. This is the
practical regression-kriging analogue available without a variogram library.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import TransformedTargetRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import RidgeCV
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from run_spatial_xgb import (
    DEFAULT_DATA,
    DEFAULT_OUT,
    add_features,
    aggregate_monthly,
    feature_columns,
    load_data,
    reliable_mask,
    spatial_cv_splits,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--time-unit", choices=["weekly", "monthly"], default="weekly")
    parser.add_argument(
        "--split", choices=["spatial-cv", "spatiotemporal-cv"], default="spatial-cv"
    )
    parser.add_argument("--target", default="salinity_max_mean")
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--monthly-min-reliable-weeks", type=int, default=2)
    parser.add_argument("--salinity-cap", type=float, default=40.0)
    parser.add_argument("--idw-power", type=float, default=2.0)
    parser.add_argument("--idw-neighbors", type=int, default=8)
    parser.add_argument(
        "--residual-source",
        choices=["contemporaneous", "historical"],
        default="contemporaneous",
        help=(
            "contemporaneous uses observed non-holdout stations at the target date; "
            "historical uses only training-period station-average residuals"
        ),
    )
    return parser.parse_args()


def projected_xy(df: pd.DataFrame) -> np.ndarray:
    """Approximate lon/lat as local kilometre coordinates for IDW distances."""
    lon = pd.to_numeric(df["lon_first"], errors="coerce").to_numpy(float)
    lat = pd.to_numeric(df["lat_first"], errors="coerce").to_numpy(float)
    lat0 = np.nanmedian(lat)
    x = lon * 111.32 * np.cos(np.deg2rad(lat0))
    y = lat * 110.57
    return np.column_stack([x, y])


def idw_predict(
    anchor_xy: np.ndarray,
    anchor_values: np.ndarray,
    query_xy: np.ndarray,
    power: float,
    neighbors: int,
) -> np.ndarray:
    valid = np.isfinite(anchor_xy).all(axis=1) & np.isfinite(anchor_values)
    anchor_xy = anchor_xy[valid]
    anchor_values = anchor_values[valid]
    result = np.full(len(query_xy), np.nan)
    if not len(anchor_values):
        return result
    for i, point in enumerate(query_xy):
        if not np.isfinite(point).all():
            continue
        distances = np.sqrt(np.sum((anchor_xy - point) ** 2, axis=1))
        exact = distances < 1e-9
        if exact.any():
            result[i] = float(np.mean(anchor_values[exact]))
            continue
        k = min(max(1, neighbors), len(distances))
        idx = np.argpartition(distances, k - 1)[:k]
        weights = 1.0 / np.power(distances[idx], power)
        result[i] = float(np.sum(weights * anchor_values[idx]) / np.sum(weights))
    return result


def ridge_model() -> TransformedTargetRegressor:
    regression = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            ("scaler", StandardScaler()),
            ("ridge", RidgeCV(alphas=np.logspace(-3, 4, 40))),
        ]
    )
    return TransformedTargetRegressor(
        regressor=regression,
        func=np.log1p,
        inverse_func=np.expm1,
        check_inverse=False,
    )


def score(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    valid = np.isfinite(y_true) & np.isfinite(y_pred)
    y_true = y_true[valid]
    y_pred = np.clip(y_pred[valid], 0.0, None)
    true_log = np.log1p(y_true)
    pred_log = np.log1p(y_pred)
    return {
        "n": int(len(y_true)),
        "r2_log": float(r2_score(true_log, pred_log)) if len(y_true) > 1 else math.nan,
        "rmse_gl": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "mae_gl": float(mean_absolute_error(y_true, y_pred)),
        "bias_gl": float(np.mean(y_pred - y_true)),
    }


def interpolate_by_date(
    df: pd.DataFrame,
    anchor_mask: pd.Series,
    query_mask: pd.Series,
    values: np.ndarray,
    power: float,
    neighbors: int,
) -> np.ndarray:
    predictions = pd.Series(np.nan, index=df.index, dtype=float)
    value_series = pd.Series(values, index=df.index[anchor_mask])
    anchors = df.loc[anchor_mask].copy()
    anchors["_value"] = value_series
    for date, query in df.loc[query_mask].groupby("date"):
        same_date = anchors[anchors["date"].eq(date)]
        if same_date.empty:
            continue
        predictions.loc[query.index] = idw_predict(
            projected_xy(same_date),
            same_date["_value"].to_numpy(float),
            projected_xy(query),
            power,
            neighbors,
        )
    return predictions.loc[df.index[query_mask]].to_numpy(float)


def historical_residual_idw(
    df: pd.DataFrame,
    train_mask: pd.Series,
    query_mask: pd.Series,
    train_residual: np.ndarray,
    power: float,
    neighbors: int,
) -> np.ndarray:
    anchors = df.loc[train_mask, ["station_id", "lon_first", "lat_first"]].copy()
    anchors["residual"] = train_residual
    anchors = anchors.groupby("station_id", as_index=False).agg(
        {"lon_first": "first", "lat_first": "first", "residual": "mean"}
    )
    return idw_predict(
        projected_xy(anchors),
        anchors["residual"].to_numpy(float),
        projected_xy(df.loc[query_mask]),
        power,
        neighbors,
    )


def main() -> None:
    args = parse_args()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out = args.output_root / f"regression_kriging_{args.time_unit}_{args.split}_{args.residual_source}_{stamp}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "config.json").write_text(
        json.dumps({k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}, indent=2),
        encoding="utf-8",
    )

    df = load_data(args.data, args.target, args.salinity_cap)
    if args.time_unit == "monthly":
        df = aggregate_monthly(df, args.monthly_min_reliable_weeks)
    df = add_features(df, include_source_format=False, include_river=False)
    features = feature_columns(df, False, False, False)
    (out / "feature_columns.txt").write_text("\n".join(features) + "\n", encoding="utf-8")
    rel = reliable_mask(df, args.target)
    splits = spatial_cv_splits(
        df, rel, args.n_splits, spatiotemporal=args.split == "spatiotemporal-cv"
    )

    metric_rows: list[dict] = []
    prediction_frames: list[pd.DataFrame] = []
    coefficient_frames: list[pd.DataFrame] = []
    for name, train, val, test, holdout_stations in splits:
        # Ridge needs no early-stopping set. In pure spatial CV, use every date
        # from non-holdout stations; spatiotemporal CV remains restricted to past years.
        fit_mask = train | val if args.split == "spatial-cv" else train
        ridge = ridge_model()
        ridge.fit(df.loc[fit_mask, features], df.loc[fit_mask, args.target])
        ridge_train = np.clip(ridge.predict(df.loc[fit_mask, features]), 0.0, None)
        ridge_test = np.clip(ridge.predict(df.loc[test, features]), 0.0, None)

        if args.residual_source == "contemporaneous":
            anchor = rel & ~df["station_id"].isin(holdout_stations)
            anchor_ridge = np.clip(ridge.predict(df.loc[anchor, features]), 0.0, None)
            anchor_residual = df.loc[anchor, args.target].to_numpy(float) - anchor_ridge
            residual_pred = interpolate_by_date(
                df, anchor, test, anchor_residual, args.idw_power, args.idw_neighbors
            )
            idw_salinity = interpolate_by_date(
                df,
                anchor,
                test,
                df.loc[anchor, args.target].to_numpy(float),
                args.idw_power,
                args.idw_neighbors,
            )
        else:
            train_residual = df.loc[fit_mask, args.target].to_numpy(float) - ridge_train
            residual_pred = historical_residual_idw(
                df, fit_mask, test, train_residual, args.idw_power, args.idw_neighbors
            )
            idw_salinity = historical_residual_idw(
                df,
                fit_mask,
                test,
                df.loc[fit_mask, args.target].to_numpy(float),
                args.idw_power,
                args.idw_neighbors,
            )

        rk_pred = np.clip(ridge_test + np.nan_to_num(residual_pred, nan=0.0), 0.0, None)
        truth = df.loc[test, args.target].to_numpy(float)
        model_predictions = {
            "ridge": ridge_test,
            "idw": idw_salinity,
            "ridge_residual_idw": rk_pred,
        }
        pred = df.loc[test, ["station_id", "date", "year", args.target]].copy()
        pred["split"] = name
        pred["y_true"] = truth
        pred["residual_correction"] = residual_pred
        for model_name, values in model_predictions.items():
            pred[f"pred_{model_name}"] = values
            metric_rows.append(
                {
                    "split": name,
                    "model": model_name,
                    "n_train": int(fit_mask.sum()),
                    "n_test": int(test.sum()),
                    "n_holdout_stations": len(holdout_stations),
                    "holdout_stations": ",".join(holdout_stations),
                    **score(truth, values),
                }
            )
        prediction_frames.append(pred)

        fitted = ridge.regressor_.named_steps["ridge"]
        coefficient_frames.append(
            pd.DataFrame(
                {
                    "split": name,
                    "alpha": fitted.alpha_,
                    "feature": [f"transformed_{i}" for i in range(len(fitted.coef_))],
                    "coefficient": fitted.coef_,
                }
            )
        )

    metrics = pd.DataFrame(metric_rows)
    metrics.to_csv(out / "metrics.csv", index=False)
    pd.concat(prediction_frames, ignore_index=True).to_csv(out / "predictions.csv", index=False)
    pd.concat(coefficient_frames, ignore_index=True).to_csv(out / "ridge_coefficients.csv", index=False)
    summary = metrics.groupby("model", as_index=False)[["r2_log", "rmse_gl", "mae_gl", "bias_gl"]].mean()
    summary.to_csv(out / "summary.csv", index=False)
    print(f"Output: {out}")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
