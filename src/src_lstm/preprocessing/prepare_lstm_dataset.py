"""Build a reproducible daily multi-source dataset for salinity LSTM models.

Inputs
------
Data/salinity_with_updated_coords.csv
Data/gee_data/era5_land_daily_22_salinity_stations_2020_2023.csv
Data/gee_data/s2_previous_month_station_composites_2020_2023.csv

Outputs
-------
Data/processed/lstm_daily_multisource_2020_2023.csv
Data/processed/lstm_data_quality_report.csv
Data/processed/lstm_station_summary.csv

The script intentionally does not interpolate long salinity gaps. It creates a
continuous station-day grid, preserves observation masks, and only applies a
causal forward fill for short input gaps. Targets remain observed-only.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
DEFAULT_SALINITY = ROOT / "Data/salinity_with_updated_coords.csv"
DEFAULT_ERA5 = ROOT / "Data/gee_data/era5_land_daily_22_salinity_stations_2020_2023.csv"
DEFAULT_S2 = ROOT / "Data/gee_data/s2_previous_month_station_composites_2020_2023.csv"
DEFAULT_OUTPUT_DIR = ROOT / "Data/processed"

START_DATE = "2020-01-01"
END_DATE = "2023-05-31"
SHORT_GAP_DAYS = 3
PHYSICAL_SALINITY_MIN = 0.0
PHYSICAL_SALINITY_MAX = 50.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--salinity", type=Path, default=DEFAULT_SALINITY)
    parser.add_argument("--era5", type=Path, default=DEFAULT_ERA5)
    parser.add_argument("--s2", type=Path, default=DEFAULT_S2)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def require_columns(df: pd.DataFrame, required: set[str], name: str) -> None:
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{name} is missing columns: {sorted(missing)}")


def load_salinity(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    sal = pd.read_csv(path, parse_dates=["date"])
    require_columns(
        sal,
        {"station_id", "date", "salinity_max", "salinity_min", "lat", "lon"},
        "salinity",
    )
    if sal.duplicated(["station_id", "date"]).any():
        raise ValueError("Salinity contains duplicate station_id/date keys")

    stations = sal[["station_id", "lat", "lon"]].drop_duplicates("station_id")
    if stations["station_id"].duplicated().any():
        raise ValueError("A station has more than one coordinate pair")

    max_invalid = sal["salinity_max"].notna() & ~sal["salinity_max"].between(
        PHYSICAL_SALINITY_MIN, PHYSICAL_SALINITY_MAX
    )
    min_invalid = sal["salinity_min"].notna() & ~sal["salinity_min"].between(
        PHYSICAL_SALINITY_MIN, PHYSICAL_SALINITY_MAX
    )
    order_invalid = (
        sal["salinity_min"].notna()
        & sal["salinity_max"].notna()
        & (sal["salinity_min"] > sal["salinity_max"])
    )
    sal["salinity_qc_invalid"] = (max_invalid | min_invalid | order_invalid).astype("int8")
    sal.loc[max_invalid | order_invalid, "salinity_max"] = np.nan
    sal.loc[min_invalid | order_invalid, "salinity_min"] = np.nan
    return sal, stations


def make_daily_grid(stations: pd.DataFrame) -> pd.DataFrame:
    dates = pd.DataFrame({"date": pd.date_range(START_DATE, END_DATE, freq="D")})
    return stations.merge(dates, how="cross")


def fill_missing_era_station(
    era: pd.DataFrame, stations: pd.DataFrame
) -> tuple[pd.DataFrame, list[str]]:
    """Copy ERA5 values from nearest station when an entire station is absent.

    ERA5-Land is coarse (~11 km), so nearest-station substitution is preferable
    to dropping a salinity station. The provenance columns make this explicit.
    """
    weather_cols = [
        c
        for c in era.columns
        if c
        not in {
            "station_id", "station_name", "lon", "lat", "date", "year", "month",
            "day", "day_of_year", "source_dataset",
        }
    ]
    present = set(era["station_id"])
    missing = sorted(set(stations["station_id"]) - present)
    additions = []
    station_lookup = stations.set_index("station_id")
    available = stations[stations["station_id"].isin(present)].copy()

    for station_id in missing:
        target = station_lookup.loc[station_id]
        distance2 = (available["lat"] - target["lat"]) ** 2 + (
            available["lon"] - target["lon"]
        ) ** 2
        donor_id = available.loc[distance2.idxmin(), "station_id"]
        donor = era.loc[era["station_id"] == donor_id, ["date", *weather_cols]].copy()
        donor["station_id"] = station_id
        donor["era5_imputed_from_station"] = donor_id
        additions.append(donor)

    base = era[["station_id", "date", *weather_cols]].copy()
    base["era5_imputed_from_station"] = pd.NA
    if additions:
        base = pd.concat([base, *additions], ignore_index=True)
    return base, missing


def prepare_s2(s2: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    require_columns(s2, {"station_id", "target_year", "target_month"}, "Sentinel-2")
    if s2.duplicated(["station_id", "target_year", "target_month"]).any():
        raise ValueError("Sentinel-2 contains duplicate station/month keys")

    drop_cols = {
        "system:index", ".geo", "lat", "lon", "target_ym",
        "buffer_m", "cloud_prob_threshold",
        "s2_prev_start", "s2_prev_end_exclusive",
    }
    value_cols = [c for c in s2.columns if c not in drop_cols]
    s2 = s2[value_cols].copy()
    rename = {
        c: f"s2_{c}"
        for c in s2.columns
        if c not in {"station_id", "target_year", "target_month"}
    }
    s2 = s2.rename(columns=rename)
    return s2, list(rename.values())


def expected_month_labels(start: str = START_DATE, end: str = END_DATE) -> list[str]:
    return pd.date_range(start, end, freq="MS").strftime("%Y-%m").tolist()


def add_salinity_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["station_id", "date"]).copy()
    df["salinity_observed"] = df["salinity_max"].notna().astype("int8")
    # Target is never filled: evaluation must use real observations only.
    df["target_salinity_max"] = df["salinity_max"]
    # LSTM input may bridge only very short gaps, using past information only.
    df["salinity_input"] = df.groupby("station_id")["salinity_max"].ffill(
        limit=SHORT_GAP_DAYS
    )
    df["salinity_input_imputed"] = (
        df["salinity_max"].isna() & df["salinity_input"].notna()
    ).astype("int8")

    observed_date = df["date"].where(df["salinity_observed"].eq(1))
    last_observed = observed_date.groupby(df["station_id"]).ffill()
    df["days_since_salinity_observed"] = (df["date"] - last_observed).dt.days
    df["days_since_salinity_observed"] = df[
        "days_since_salinity_observed"
    ].fillna(9999).astype("int16")
    return df


def build_dataset(args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    sal, stations = load_salinity(args.salinity)
    grid = make_daily_grid(stations)
    sal_cols = [
        "station_id", "date", "salinity_max", "salinity_min", "source_type",
        "salinity_qc_invalid",
    ]
    df = grid.merge(sal[sal_cols], on=["station_id", "date"], how="left", validate="1:1")

    era = pd.read_csv(args.era5, parse_dates=["date"])
    require_columns(era, {"station_id", "date"}, "ERA5")
    if era.duplicated(["station_id", "date"]).any():
        raise ValueError("ERA5 contains duplicate station_id/date keys")
    era, missing_era_stations = fill_missing_era_station(era, stations)
    df = df.merge(era, on=["station_id", "date"], how="left", validate="1:1")

    s2_raw = pd.read_csv(args.s2)
    s2, s2_feature_cols = prepare_s2(s2_raw)
    s2_month_labels = (
        pd.to_datetime(
            dict(year=s2_raw["target_year"], month=s2_raw["target_month"], day=1)
        )
        .dt.strftime("%Y-%m")
        .unique()
        .tolist()
    )
    missing_s2_months = sorted(set(expected_month_labels()) - set(s2_month_labels))
    df["year"] = df["date"].dt.year.astype("int16")
    df["month"] = df["date"].dt.month.astype("int8")
    df["day"] = df["date"].dt.day.astype("int8")
    df["day_of_year"] = df["date"].dt.dayofyear.astype("int16")
    df = df.merge(
        s2,
        left_on=["station_id", "year", "month"],
        right_on=["station_id", "target_year", "target_month"],
        how="left",
        validate="m:1",
    ).drop(columns=["target_year", "target_month"])
    df["s2_month_available"] = df[s2_feature_cols].notna().any(axis=1).astype("int8")

    angle = 2 * np.pi * df["day_of_year"] / 365.25
    df["day_of_year_sin"] = np.sin(angle)
    df["day_of_year_cos"] = np.cos(angle)
    df = add_salinity_features(df)

    quality = pd.DataFrame(
        [
            ("daily_grid_rows", len(df)),
            ("station_count", df["station_id"].nunique()),
            ("start_date", df["date"].min().date().isoformat()),
            ("end_date", df["date"].max().date().isoformat()),
            ("salinity_max_observed_rows", int(df["salinity_observed"].sum())),
            ("salinity_qc_invalid_rows", int(df["salinity_qc_invalid"].fillna(0).sum())),
            ("short_gap_salinity_filled_rows", int(df["salinity_input_imputed"].sum())),
            ("era5_missing_stations_filled_from_nearest", ",".join(missing_era_stations)),
            ("era5_rows_with_any_missing", int(df.filter(regex="temperature|precipitation|wind|runoff|pressure|soil|solar|evaporation").isna().any(axis=1).sum())),
            ("era5_buffer_m_values", ",".join(str(v) for v in sorted(df["era5_buffer_m"].dropna().unique())) if "era5_buffer_m" in df else ""),
            ("s2_source_month_count", len(s2_month_labels)),
            ("s2_missing_target_months", ",".join(missing_s2_months)),
            ("s2_month_available_rows", int(df["s2_month_available"].sum())),
            ("s2_month_missing_rows", int(df["s2_month_available"].eq(0).sum())),
        ],
        columns=["metric", "value"],
    )
    station_summary = (
        df.groupby("station_id", as_index=False)
        .agg(
            total_days=("date", "size"),
            salinity_observed_days=("salinity_observed", "sum"),
            salinity_short_gap_filled_days=("salinity_input_imputed", "sum"),
            salinity_input_available_days=("salinity_input", "count"),
            s2_available_days=("s2_month_available", "sum"),
            era5_proxy_station=("era5_imputed_from_station", "first"),
        )
    )
    return df, quality, station_summary


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    dataset, quality, station_summary = build_dataset(args)
    dataset.to_csv(args.output_dir / "lstm_daily_multisource_2020_2023.csv", index=False)
    quality.to_csv(args.output_dir / "lstm_data_quality_report.csv", index=False)
    station_summary.to_csv(args.output_dir / "lstm_station_summary.csv", index=False)
    print(quality.to_string(index=False))


if __name__ == "__main__":
    main()
