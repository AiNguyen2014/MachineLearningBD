"""Train a reproducible monthly Ridge drift and map March 2023 salinity.

The supplied GEE grid is filtered to water-like pixels near HydroSHEDS rivers.
March 2023 observations at existing stations are used only as residual anchors;
grid locations never have salinity labels.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from run_regression_kriging import idw_predict, projected_xy, ridge_model
from run_spatial_xgb import (
    DEFAULT_DATA,
    add_features,
    aggregate_monthly,
    load_data,
    reliable_mask,
    spatial_cv_splits,
)


ROOT = Path(__file__).resolve().parent
DEFAULT_GRID = ROOT / "data/mekong_covariates_2023_03_monthly.csv"
DEFAULT_OUTPUT = ROOT / "outputs/monthly_grid_2023_03"

FEATURES = [
    "lon_first", "lat_first", "DEM_first",
    "month_sin", "month_cos",
    "temperature_2m_c_mean", "precipitation_mm_sum",
    "potential_evaporation_mm_sum", "runoff_mm_sum", "runoff_mm_max",
    "surface_pressure_hpa_min", "soil_moisture_layer1_vol_mean",
    "solar_radiation_mj_m2_sum",
    "MNDWI_median_week", "NDWI_median_week", "NDVI_median_week",
    "B11_median_week", "B12_median_week", "Red_SWIR1_median_week",
    "Red_SWIR2_median_week", "BGRratio_median_week", "NDCI_median_week",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--grid", type=Path, default=DEFAULT_GRID)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--target", default="salinity_max_mean")
    parser.add_argument("--idw-power", type=float, default=2.0)
    parser.add_argument("--idw-neighbors", type=int, default=8)
    parser.add_argument("--river-corridor-m", type=float, default=5000.0)
    return parser.parse_args()


def prepare_grid(path: Path, river_corridor_m: float) -> tuple[pd.DataFrame, dict]:
    raw = pd.read_csv(path)
    raw["date"] = pd.to_datetime(raw["period_start"])
    raw["year"] = raw["date"].dt.year
    raw["month"] = raw["date"].dt.month
    raw["month_sin"] = np.sin(2 * np.pi * raw["month"] / 12)
    raw["month_cos"] = np.cos(2 * np.pi * raw["month"] / 12)

    # ERA5-Land encodes evaporation as an upward (negative) flux in GEE.
    evap = pd.to_numeric(raw["potential_evaporation_mm_sum"], errors="coerce")
    if evap.median(skipna=True) < 0:
        raw["potential_evaporation_mm_sum"] = -evap

    water = raw["MNDWI_median_week"].gt(0) & raw["NDVI_median_week"].lt(0)
    near_river = (
        raw["Distance_to_River_first"].le(river_corridor_m)
        if "Distance_to_River_first" in raw
        else pd.Series(True, index=raw.index)
    )
    valid_xy = raw[["lon_first", "lat_first"]].notna().all(axis=1)
    grid = raw.loc[water & near_river & valid_xy].copy()
    grid = grid.drop_duplicates("grid_id").reset_index(drop=True)
    audit = {
        "raw_grid_rows": int(len(raw)),
        "water_like_rows": int(water.sum()),
        "near_river_rows": int(near_river.sum()),
        "mapping_rows": int(len(grid)),
        "river_corridor_m": river_corridor_m,
        "potential_evaporation_sign_corrected": bool(evap.median(skipna=True) < 0),
    }
    return grid, audit


def metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    valid = np.isfinite(y_true) & np.isfinite(y_pred)
    y_true, y_pred = y_true[valid], np.clip(y_pred[valid], 0, None)
    return {
        "n": int(len(y_true)),
        "r2_log": float(r2_score(np.log1p(y_true), np.log1p(y_pred))),
        "rmse_gl": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "mae_gl": float(mean_absolute_error(y_true, y_pred)),
        "bias_gl": float(np.mean(y_pred - y_true)),
    }


def validate_features(train: pd.DataFrame, grid: pd.DataFrame) -> list[str]:
    missing_train = [c for c in FEATURES if c not in train]
    missing_grid = [c for c in FEATURES if c not in grid]
    if missing_train or missing_grid:
        raise ValueError(f"Missing features; train={missing_train}, grid={missing_grid}")
    return FEATURES


def evaluate_spatial_cv(df: pd.DataFrame, rel: pd.Series, features: list[str]) -> pd.DataFrame:
    rows = []
    splits = spatial_cv_splits(df, rel, n_splits=5, spatiotemporal=False)
    for name, train, val, test, holdout in splits:
        fit = train | val
        reg = ridge_model().fit(df.loc[fit, features], df.loc[fit, "salinity_max_mean"])
        pred = np.clip(reg.predict(df.loc[test, features]), 0, None)
        rows.append({"split": name, "model": "ridge_reproducible", **metrics(df.loc[test, "salinity_max_mean"].to_numpy(), pred)})

        anchor = rel & ~df["station_id"].isin(holdout)
        anchor_pred = np.clip(reg.predict(df.loc[anchor, features]), 0, None)
        anchor_residual = df.loc[anchor, "salinity_max_mean"].to_numpy() - anchor_pred
        correction = np.full(test.sum(), np.nan)
        test_indices = df.index[test]
        for (year, month), q in df.loc[test].groupby(["year", "month"]):
            a = df.loc[anchor & df["year"].eq(year) & df["month"].eq(month)]
            if a.empty:
                continue
            vals = pd.Series(anchor_residual, index=df.index[anchor]).loc[a.index].to_numpy()
            pos = test_indices.get_indexer(q.index)
            correction[pos] = idw_predict(projected_xy(a), vals, projected_xy(q), 2.0, 8)
        combined = np.clip(pred + np.nan_to_num(correction), 0, None)
        rows.append({"split": name, "model": "ridge_residual_idw_reproducible", **metrics(df.loc[test, "salinity_max_mean"].to_numpy(), combined)})
    return pd.DataFrame(rows)


def nearest_distance_km(anchor: pd.DataFrame, query: pd.DataFrame) -> np.ndarray:
    axy, qxy = projected_xy(anchor), projected_xy(query)
    return np.array([np.sqrt(np.sum((axy - q) ** 2, axis=1)).min() for q in qxy])


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    station = load_data(args.data, args.target, 40.0)
    station = aggregate_monthly(station, min_reliable_weeks=2)
    station = add_features(station, include_source_format=False, include_river=False)
    grid, audit = prepare_grid(args.grid, args.river_corridor_m)
    features = validate_features(station, grid)
    rel = reliable_mask(station, args.target)

    cv = evaluate_spatial_cv(station, rel, features)
    cv.to_csv(args.output_dir / "spatial_cv_metrics.csv", index=False)
    cv.groupby("model", as_index=False)[["r2_log", "rmse_gl", "mae_gl", "bias_gl"]].mean().to_csv(
        args.output_dir / "spatial_cv_summary.csv", index=False
    )

    target_date = grid["date"].iloc[0]
    past = rel & station["date"].lt(target_date)
    anchors = station.loc[
        rel & station["year"].eq(target_date.year) & station["month"].eq(target_date.month)
    ].copy()
    if anchors.empty:
        raise ValueError(f"No contemporaneous station anchors for {target_date.date()}")
    reg = ridge_model().fit(station.loc[past, features], station.loc[past, args.target])
    ridge_grid = np.clip(reg.predict(grid[features]), 0, None)
    ridge_anchor = np.clip(reg.predict(anchors[features]), 0, None)
    anchor_residual = anchors[args.target].to_numpy() - ridge_anchor
    residual_grid = idw_predict(
        projected_xy(anchors), anchor_residual, projected_xy(grid), args.idw_power, args.idw_neighbors
    )
    idw_grid = idw_predict(
        projected_xy(anchors), anchors[args.target].to_numpy(), projected_xy(grid), args.idw_power, args.idw_neighbors
    )

    out = grid[["grid_id", "date", "lon_first", "lat_first", "MNDWI_median_week", "NDVI_median_week"]].copy()
    out["pred_ridge_gl"] = ridge_grid
    out["residual_idw_gl"] = residual_grid
    out["pred_ridge_residual_idw_gl"] = np.clip(ridge_grid + residual_grid, 0, None)
    out["pred_idw_gl"] = np.clip(idw_grid, 0, None)
    out["nearest_anchor_km"] = nearest_distance_km(anchors, grid)
    out["extrapolation_zone"] = pd.cut(
        out["nearest_anchor_km"], bins=[-np.inf, 25, 50, np.inf], labels=["near_0_25km", "medium_25_50km", "far_over_50km"]
    ).astype(str)
    out.to_csv(args.output_dir / "grid_predictions_2023_03.csv", index=False)
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [row.lon_first, row.lat_first]},
                "properties": {
                    "grid_id": row.grid_id,
                    "salinity_gl": row.pred_ridge_residual_idw_gl,
                    "ridge_gl": row.pred_ridge_gl,
                    "residual_gl": row.residual_idw_gl,
                    "nearest_anchor_km": row.nearest_anchor_km,
                    "extrapolation_zone": row.extrapolation_zone,
                },
            }
            for row in out.itertuples(index=False)
        ],
    }
    (args.output_dir / "grid_predictions_2023_03.geojson").write_text(
        json.dumps(geojson), encoding="utf-8"
    )
    anchors[["station_id", "date", "lon_first", "lat_first", args.target]].assign(
        pred_ridge_gl=ridge_anchor, residual_gl=anchor_residual
    ).to_csv(args.output_dir / "residual_anchors_2023_03.csv", index=False)

    audit.update({
        "target_date": str(target_date.date()),
        "past_training_rows": int(past.sum()),
        "anchor_station_count": int(anchors["station_id"].nunique()),
        "features": features,
        "nearest_anchor_km_summary": out["nearest_anchor_km"].describe().to_dict(),
    })
    (args.output_dir / "mapping_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(json.dumps(audit, indent=2))
    print("\nSpatial CV mean:")
    print(cv.groupby("model")[["r2_log", "rmse_gl", "mae_gl"]].mean().to_string())
    print("\nPrediction summary:")
    print(out[["pred_ridge_gl", "pred_ridge_residual_idw_gl", "pred_idw_gl", "nearest_anchor_km"]].describe().to_string())


if __name__ == "__main__":
    main()
