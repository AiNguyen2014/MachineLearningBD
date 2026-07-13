"""Correlation diagnostics for spatial XGBoost features.

This script checks whether map-ready variables have a detectable association
with salinity labels. It intentionally excludes station identity, salinity lags,
source format, and protocol-quality fields by default.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from run_spatial_xgb import (
    DEFAULT_DATA,
    DEFAULT_OUT,
    add_features,
    aggregate_monthly,
    feature_columns,
    load_data,
    reliable_mask,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--target", default="salinity_max_mean")
    parser.add_argument("--salinity-cap", type=float, default=40.0)
    parser.add_argument("--monthly-min-reliable-weeks", type=int, default=2)
    parser.add_argument("--min-n", type=int, default=20)
    return parser.parse_args()


def pearson(x: pd.Series, y: pd.Series) -> float:
    valid = x.notna() & y.notna()
    if valid.sum() < 3:
        return np.nan
    return float(x[valid].corr(y[valid], method="pearson"))


def spearman(x: pd.Series, y: pd.Series) -> float:
    valid = x.notna() & y.notna()
    if valid.sum() < 3:
        return np.nan
    return float(x[valid].corr(y[valid], method="spearman"))


def correlation_table(df: pd.DataFrame, features: list[str], target: str, min_n: int) -> pd.DataFrame:
    rows = []
    y = df[target]
    y_log = np.log1p(y)
    for col in features:
        valid = df[col].notna() & y.notna()
        n = int(valid.sum())
        if n < min_n:
            continue
        rows.append({
            "feature": col,
            "n": n,
            "missing_pct": float(1 - df[col].notna().mean()),
            "pearson_target": pearson(df[col], y),
            "spearman_target": spearman(df[col], y),
            "pearson_log_target": pearson(df[col], y_log),
            "spearman_log_target": spearman(df[col], y_log),
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["abs_spearman_log_target"] = out["spearman_log_target"].abs()
    return out.sort_values("abs_spearman_log_target", ascending=False)


def add_groups(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["season_group"] = np.where(out["month"].isin([12, 1, 2, 3, 4, 5]), "dry", "wet")
    if out["Distance_to_Coast_first"].notna().sum() >= 3:
        out["coast_distance_group"] = pd.qcut(
            out["Distance_to_Coast_first"].rank(method="first"),
            q=3,
            labels=["near_coast", "mid_coast", "far_coast"],
        )
    else:
        out["coast_distance_group"] = "unknown"
    return out


def run_one(time_unit: str, args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    df = load_data(args.data, args.target, args.salinity_cap)
    if time_unit == "monthly":
        df = aggregate_monthly(df, args.monthly_min_reliable_weeks)
    df = add_features(df, include_source_format=False, include_river=False)
    df = add_groups(df)
    features = feature_columns(
        df,
        include_completeness=False,
        include_source_format=False,
        include_river=False,
    )
    rel = reliable_mask(df, args.target)
    analysis_df = df[rel].copy()
    overall = correlation_table(analysis_df, features, args.target, args.min_n)
    overall.insert(0, "time_unit", time_unit)
    overall.insert(1, "group_type", "overall")
    overall.insert(2, "group", "all")

    grouped_rows = []
    for group_type in ["season_group", "coast_distance_group"]:
        for group, sub in analysis_df.groupby(group_type, dropna=False):
            tab = correlation_table(sub, features, args.target, args.min_n)
            if tab.empty:
                continue
            tab.insert(0, "time_unit", time_unit)
            tab.insert(1, "group_type", group_type)
            tab.insert(2, "group", str(group))
            grouped_rows.append(tab)
    grouped = pd.concat(grouped_rows, ignore_index=True) if grouped_rows else pd.DataFrame()

    feature_groups = []
    for feature in features:
        if feature in {"lon_first", "lat_first", "DEM_first", "Distance_to_River_first", "Distance_to_Coast_first"}:
            kind = "static"
        elif feature.endswith("_median_week") or feature == "s2_available":
            kind = "spectral"
        elif feature.endswith("_sin") or feature.endswith("_cos"):
            kind = "season"
        else:
            kind = "weather"
        feature_groups.append({"feature": feature, "feature_group": kind})
    groups = pd.DataFrame(feature_groups)
    return overall.merge(groups, on="feature", how="left"), grouped.merge(groups, on="feature", how="left"), groups


def main() -> None:
    args = parse_args()
    output_dir = args.output_root / "correlations"
    output_dir.mkdir(parents=True, exist_ok=True)
    overall_tables = []
    grouped_tables = []
    for unit in ["weekly", "monthly"]:
        overall, grouped, groups = run_one(unit, args)
        overall_tables.append(overall)
        if not grouped.empty:
            grouped_tables.append(grouped)
    overall = pd.concat(overall_tables, ignore_index=True)
    grouped = pd.concat(grouped_tables, ignore_index=True) if grouped_tables else pd.DataFrame()
    overall.to_csv(output_dir / "overall_feature_correlations.csv", index=False)
    grouped.to_csv(output_dir / "grouped_feature_correlations.csv", index=False)

    summary = (
        overall.groupby(["time_unit", "feature_group"], as_index=False)
        .agg(
            n_features=("feature", "count"),
            median_abs_spearman_log=("abs_spearman_log_target", "median"),
            max_abs_spearman_log=("abs_spearman_log_target", "max"),
        )
        .sort_values(["time_unit", "max_abs_spearman_log"], ascending=[True, False])
    )
    summary.to_csv(output_dir / "feature_group_correlation_summary.csv", index=False)
    print(f"Output: {output_dir}")
    print("\nTop overall correlations:")
    print(overall.sort_values("abs_spearman_log_target", ascending=False).head(20).to_string(index=False))
    print("\nFeature group summary:")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()

