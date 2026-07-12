"""Create EDA tables and lightweight SVG figures for the LSTM dataset.

Inputs
------
Data/processed/lstm_daily_multisource_2020_2023.csv
Data/salinity_with_updated_coords.csv
Data/gee_data/era5_land_daily_22_salinity_stations_2020_2023.csv
Data/gee_data/s2_previous_month_station_composites_2020_2023.csv

Outputs
-------
Data/eda/eda_overview_metrics.csv
Data/eda/eda_station_coverage.csv
Data/eda/eda_monthly_coverage.csv
Data/eda/eda_feature_missingness.csv
Data/eda/eda_salinity_monthly_stats.csv
Data/eda/eda_feature_correlations.csv
Data/eda/paper_data_summary.md
Data/eda/*.svg
"""

from __future__ import annotations

import argparse
import html
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
DEFAULT_DATASET = ROOT / "Data/processed/lstm_daily_multisource_2020_2023.csv"
DEFAULT_SALINITY = ROOT / "Data/salinity_with_updated_coords.csv"
DEFAULT_ERA5 = ROOT / "Data/gee_data/era5_land_daily_22_salinity_stations_2020_2023.csv"
DEFAULT_S2 = ROOT / "Data/gee_data/s2_previous_month_station_composites_2020_2023.csv"
DEFAULT_OUTPUT_DIR = ROOT / "Data/eda"

ID_COLUMNS = {
    "station_id", "lat", "lon", "date", "source_type", "year", "month", "day",
    "day_of_year", "source_dataset", "era5_imputed_from_station",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--salinity", type=Path, default=DEFAULT_SALINITY)
    parser.add_argument("--era5", type=Path, default=DEFAULT_ERA5)
    parser.add_argument("--s2", type=Path, default=DEFAULT_S2)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def pct(numerator: float, denominator: float) -> float:
    return float(numerator / denominator * 100) if denominator else 0.0


def read_inputs(args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    df = pd.read_csv(args.dataset, parse_dates=["date"])
    salinity = pd.read_csv(args.salinity, parse_dates=["date"])
    era5 = pd.read_csv(args.era5, parse_dates=["date"])
    s2 = pd.read_csv(args.s2)
    return df, salinity, era5, s2


def build_overview(df: pd.DataFrame, salinity: pd.DataFrame, era5: pd.DataFrame, s2: pd.DataFrame) -> pd.DataFrame:
    s2_months = pd.to_datetime(
        dict(year=s2["target_year"], month=s2["target_month"], day=1)
    ).dt.strftime("%Y-%m")
    expected_months = pd.date_range(df["date"].min(), df["date"].max(), freq="MS").strftime("%Y-%m")
    missing_s2_months = sorted(set(expected_months) - set(s2_months))
    weather_cols = df.filter(regex="temperature|precipitation|wind|runoff|pressure|soil|solar|evaporation").columns
    overview = [
        ("station_count", df["station_id"].nunique()),
        ("daily_grid_rows", len(df)),
        ("date_start", df["date"].min().date().isoformat()),
        ("date_end", df["date"].max().date().isoformat()),
        ("salinity_raw_rows", len(salinity)),
        ("salinity_observed_rows_after_qc", int(df["salinity_observed"].sum())),
        ("salinity_observed_pct_of_grid", round(pct(df["salinity_observed"].sum(), len(df)), 2)),
        ("salinity_qc_invalid_rows", int(df["salinity_qc_invalid"].fillna(0).sum())),
        ("short_gap_salinity_filled_rows", int(df["salinity_input_imputed"].sum())),
        ("era5_rows", len(era5)),
        ("era5_station_count", era5["station_id"].nunique()),
        ("era5_rows_with_any_missing", int(df[weather_cols].isna().any(axis=1).sum())),
        ("era5_buffer_m_values", ",".join(str(v) for v in sorted(df["era5_buffer_m"].dropna().unique())) if "era5_buffer_m" in df else ""),
        ("s2_rows", len(s2)),
        ("s2_station_count", s2["station_id"].nunique()),
        ("s2_target_month_count", s2_months.nunique()),
        ("s2_target_month_start", s2_months.min()),
        ("s2_target_month_end", s2_months.max()),
        ("s2_missing_target_months", ",".join(missing_s2_months)),
        ("s2_available_daily_rows", int(df["s2_month_available"].sum())),
        ("s2_missing_daily_rows", int(df["s2_month_available"].eq(0).sum())),
    ]
    return pd.DataFrame(overview, columns=["metric", "value"])


def build_station_coverage(df: pd.DataFrame) -> pd.DataFrame:
    station = (
        df.groupby("station_id", as_index=False)
        .agg(
            total_days=("date", "size"),
            first_date=("date", "min"),
            last_date=("date", "max"),
            salinity_observed_days=("salinity_observed", "sum"),
            salinity_short_gap_filled_days=("salinity_input_imputed", "sum"),
            salinity_input_available_days=("salinity_input", "count"),
            s2_available_days=("s2_month_available", "sum"),
            salinity_mean=("target_salinity_max", "mean"),
            salinity_std=("target_salinity_max", "std"),
            salinity_min=("target_salinity_max", "min"),
            salinity_max=("target_salinity_max", "max"),
        )
    )
    station["salinity_observed_pct"] = station.apply(
        lambda r: pct(r["salinity_observed_days"], r["total_days"]), axis=1
    ).round(2)
    station["s2_available_pct"] = station.apply(
        lambda r: pct(r["s2_available_days"], r["total_days"]), axis=1
    ).round(2)
    return station.sort_values("salinity_observed_days", ascending=False)


def build_monthly_coverage(df: pd.DataFrame) -> pd.DataFrame:
    monthly = df.copy()
    monthly["year_month"] = monthly["date"].dt.to_period("M").astype(str)
    out = (
        monthly.groupby("year_month", as_index=False)
        .agg(
            total_station_days=("date", "size"),
            salinity_observed_days=("salinity_observed", "sum"),
            s2_available_days=("s2_month_available", "sum"),
            salinity_mean=("target_salinity_max", "mean"),
            salinity_std=("target_salinity_max", "std"),
            salinity_max=("target_salinity_max", "max"),
            precipitation_mean_mm=("precipitation_mm", "mean"),
            precipitation_sum_mm_station_days=("precipitation_mm", "sum"),
            potential_evaporation_mean_mm=("potential_evaporation_mm", "mean"),
        )
    )
    out["salinity_observed_pct"] = out.apply(
        lambda r: pct(r["salinity_observed_days"], r["total_station_days"]), axis=1
    ).round(2)
    out["s2_available_pct"] = out.apply(
        lambda r: pct(r["s2_available_days"], r["total_station_days"]), axis=1
    ).round(2)
    return out


def build_missingness(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col in df.columns:
        missing = int(df[col].isna().sum())
        rows.append(
            {
                "column": col,
                "dtype": str(df[col].dtype),
                "missing_rows": missing,
                "missing_pct": round(pct(missing, len(df)), 2),
                "non_missing_rows": int(df[col].notna().sum()),
            }
        )
    return pd.DataFrame(rows).sort_values(["missing_pct", "column"], ascending=[False, True])


def build_salinity_monthly_stats(df: pd.DataFrame) -> pd.DataFrame:
    observed = df[df["salinity_observed"].eq(1)].copy()
    observed["year_month"] = observed["date"].dt.to_period("M").astype(str)
    return (
        observed.groupby(["year_month", "station_id"], as_index=False)
        .agg(
            observed_days=("target_salinity_max", "count"),
            salinity_mean=("target_salinity_max", "mean"),
            salinity_median=("target_salinity_max", "median"),
            salinity_std=("target_salinity_max", "std"),
            salinity_min=("target_salinity_max", "min"),
            salinity_max=("target_salinity_max", "max"),
        )
        .sort_values(["year_month", "station_id"])
    )


def build_correlations(df: pd.DataFrame) -> pd.DataFrame:
    observed = df[df["target_salinity_max"].notna()].copy()
    numeric_cols = [
        c for c in observed.select_dtypes(include=[np.number]).columns
        if c not in ID_COLUMNS
        and c not in {
            "salinity_max", "salinity_min", "target_salinity_max",
            "salinity_input",
            "salinity_observed", "salinity_qc_invalid", "salinity_input_imputed",
        }
    ]
    rows = []
    for col in numeric_cols:
        pair = observed[[col, "target_salinity_max"]].dropna()
        if len(pair) < 100 or pair[col].nunique() < 2:
            continue
        corr = pair[col].corr(pair["target_salinity_max"])
        if pd.notna(corr):
            rows.append(
                {
                    "feature": col,
                    "pearson_corr_with_salinity_max": corr,
                    "abs_corr": abs(corr),
                    "pair_count": len(pair),
                }
            )
    return pd.DataFrame(rows).sort_values("abs_corr", ascending=False)


def scale_points(values: list[float], width: int, height: int, pad: int) -> list[tuple[float, float]]:
    if not values:
        return []
    vmin = min(values)
    vmax = max(values)
    span = vmax - vmin if vmax != vmin else 1.0
    step = (width - 2 * pad) / max(len(values) - 1, 1)
    points = []
    for i, value in enumerate(values):
        x = pad + i * step
        y = height - pad - (value - vmin) / span * (height - 2 * pad)
        points.append((x, y))
    return points


def save_line_svg(path: Path, title: str, labels: list[str], values: list[float]) -> None:
    width, height, pad = 920, 360, 54
    points = scale_points(values, width, height, pad)
    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    circles = "\n".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="#2f6f73"/>' for x, y in points)
    ticks = []
    if labels:
        for idx in np.linspace(0, len(labels) - 1, min(8, len(labels))).round().astype(int):
            x = points[idx][0] if points else pad
            ticks.append(f'<text x="{x:.1f}" y="{height - 16}" text-anchor="middle" font-size="11">{html.escape(labels[idx])}</text>')
    vmin = min(values) if values else 0
    vmax = max(values) if values else 0
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<rect width="100%" height="100%" fill="white"/>
<text x="{pad}" y="28" font-family="Arial" font-size="18" font-weight="700">{html.escape(title)}</text>
<line x1="{pad}" y1="{height-pad}" x2="{width-pad}" y2="{height-pad}" stroke="#888"/>
<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{height-pad}" stroke="#888"/>
<text x="{pad}" y="{pad-14}" font-family="Arial" font-size="11">{vmax:.2f}</text>
<text x="{pad}" y="{height-pad+18}" font-family="Arial" font-size="11">{vmin:.2f}</text>
<polyline points="{polyline}" fill="none" stroke="#2f6f73" stroke-width="2.5"/>
{circles}
{''.join(ticks)}
</svg>
'''
    path.write_text(svg, encoding="utf-8")


def save_bar_svg(path: Path, title: str, labels: list[str], values: list[float], unit: str = "") -> None:
    width, height, pad = 980, 430, 70
    n = len(values)
    vmax = max(values) if values else 1.0
    bar_area = width - 2 * pad
    bar_w = max(8, bar_area / max(n, 1) * 0.72)
    gap = bar_area / max(n, 1) * 0.28
    bars = []
    label_step = max(1, int(np.ceil(n / 14)))
    for i, (label, value) in enumerate(zip(labels, values)):
        x = pad + i * (bar_w + gap)
        h = (value / vmax) * (height - 2 * pad) if vmax else 0
        y = height - pad - h
        bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" fill="#52796f"/>')
        if i % label_step == 0:
            bars.append(
                f'<text transform="translate({x + bar_w/2:.1f},{height - 18}) rotate(-35)" '
                f'text-anchor="end" font-family="Arial" font-size="10">{html.escape(label)}</text>'
            )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<rect width="100%" height="100%" fill="white"/>
<text x="{pad}" y="30" font-family="Arial" font-size="18" font-weight="700">{html.escape(title)}</text>
<line x1="{pad}" y1="{height-pad}" x2="{width-pad}" y2="{height-pad}" stroke="#888"/>
<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{height-pad}" stroke="#888"/>
<text x="{pad}" y="{pad-14}" font-family="Arial" font-size="11">{vmax:.1f}{html.escape(unit)}</text>
{''.join(bars)}
</svg>
'''
    path.write_text(svg, encoding="utf-8")


def write_figures(output_dir: Path, station: pd.DataFrame, monthly: pd.DataFrame, corr: pd.DataFrame) -> None:
    save_bar_svg(
        output_dir / "station_salinity_observation_coverage.svg",
        "Salinity Observation Coverage by Station (%)",
        station.sort_values("salinity_observed_pct", ascending=False)["station_id"].tolist(),
        station.sort_values("salinity_observed_pct", ascending=False)["salinity_observed_pct"].tolist(),
        "%",
    )
    save_bar_svg(
        output_dir / "monthly_salinity_observed_days.svg",
        "Observed Salinity Station-Days by Month",
        monthly["year_month"].tolist(),
        monthly["salinity_observed_days"].tolist(),
    )
    line = monthly.dropna(subset=["salinity_mean"])
    save_line_svg(
        output_dir / "monthly_mean_salinity.svg",
        "Monthly Mean Salinity Max",
        line["year_month"].tolist(),
        line["salinity_mean"].tolist(),
    )
    if not corr.empty:
        top = corr.head(20).sort_values("abs_corr")
        save_bar_svg(
            output_dir / "top_feature_correlations.svg",
            "Top Absolute Pearson Correlations with Salinity Max",
            top["feature"].tolist(),
            top["abs_corr"].tolist(),
        )


def write_paper_summary(
    path: Path,
    overview: pd.DataFrame,
    station: pd.DataFrame,
    monthly: pd.DataFrame,
    corr: pd.DataFrame,
) -> None:
    metrics = dict(zip(overview["metric"], overview["value"]))
    best_station = station.sort_values("salinity_observed_pct", ascending=False).iloc[0]
    weakest_station = station.sort_values("salinity_observed_pct", ascending=True).iloc[0]
    peak_month = monthly.sort_values("salinity_mean", ascending=False).dropna(subset=["salinity_mean"]).iloc[0]
    top_corr = corr.head(10)
    corr_lines = "\n".join(
        f"- `{row.feature}`: r = {row.pearson_corr_with_salinity_max:.3f}, n = {int(row.pair_count)}"
        for row in top_corr.itertuples()
    )
    text = f"""# Data EDA Summary for Paper

## Dataset Scope

- Daily modelling grid: {metrics['daily_grid_rows']} station-days from {metrics['date_start']} to {metrics['date_end']} across {metrics['station_count']} salinity stations.
- Observed salinity after QC: {metrics['salinity_observed_rows_after_qc']} station-days, equivalent to {metrics['salinity_observed_pct_of_grid']}% of the full daily grid.
- One salinity row was marked invalid by physical QC and excluded from the target/input value.
- Short causal forward-fill for salinity inputs filled {metrics['short_gap_salinity_filled_rows']} station-days. The target column remains observed-only.

## Multi-Source Coverage

- ERA5-Land daily weather rows: {metrics['era5_rows']} rows across {metrics['era5_station_count']} stations, with {metrics['era5_rows_with_any_missing']} station-days containing missing weather values after merging.
- ERA5 extraction buffer values in the processed dataset: {metrics['era5_buffer_m_values']} m. This should be reported as buffered ERA5-Land extraction, not exact point sampling.
- Sentinel-2 previous-month composites: {metrics['s2_rows']} rows across {metrics['s2_station_count']} stations and {metrics['s2_target_month_count']} target months ({metrics['s2_target_month_start']} to {metrics['s2_target_month_end']}).
- Missing Sentinel-2 target months relative to the daily grid: {metrics['s2_missing_target_months'] or 'none'}.

## Salinity Coverage Notes

- Highest salinity observation coverage: {best_station.station_id} with {best_station.salinity_observed_pct:.2f}% of station-days observed.
- Lowest salinity observation coverage: {weakest_station.station_id} with {weakest_station.salinity_observed_pct:.2f}% of station-days observed.
- Highest monthly mean observed salinity: {peak_month.year_month}, mean = {peak_month.salinity_mean:.2f}, max = {peak_month.salinity_max:.2f}.

## Top Linear Associations

The following Pearson correlations are computed only on rows with observed salinity target values. They are descriptive EDA values, not model evidence:

{corr_lines}

## Files Generated

- `eda_overview_metrics.csv`: overall source and merged-dataset metrics.
- `eda_station_coverage.csv`: station-level salinity and Sentinel-2 coverage.
- `eda_monthly_coverage.csv`: month-level observation and weather summaries.
- `eda_feature_missingness.csv`: missingness by column.
- `eda_salinity_monthly_stats.csv`: station-month salinity statistics.
- `eda_feature_correlations.csv`: descriptive Pearson correlations with salinity max.
- SVG figures in this folder can be opened directly in a browser or inserted into the report.
"""
    path.write_text(text, encoding="utf-8")


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    df, salinity, era5, s2 = read_inputs(args)

    overview = build_overview(df, salinity, era5, s2)
    station = build_station_coverage(df)
    monthly = build_monthly_coverage(df)
    missingness = build_missingness(df)
    salinity_monthly = build_salinity_monthly_stats(df)
    correlations = build_correlations(df)

    overview.to_csv(args.output_dir / "eda_overview_metrics.csv", index=False)
    station.to_csv(args.output_dir / "eda_station_coverage.csv", index=False)
    monthly.to_csv(args.output_dir / "eda_monthly_coverage.csv", index=False)
    missingness.to_csv(args.output_dir / "eda_feature_missingness.csv", index=False)
    salinity_monthly.to_csv(args.output_dir / "eda_salinity_monthly_stats.csv", index=False)
    correlations.to_csv(args.output_dir / "eda_feature_correlations.csv", index=False)

    write_figures(args.output_dir, station, monthly, correlations)
    write_paper_summary(args.output_dir / "paper_data_summary.md", overview, station, monthly, correlations)
    print(overview.to_string(index=False))
    print(f"\nEDA outputs written to {args.output_dir}")


if __name__ == "__main__":
    main()
