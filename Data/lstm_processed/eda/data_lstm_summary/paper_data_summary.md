# Data EDA Summary for Paper

## Dataset Scope

- Daily modelling grid: 27434 station-days from 2020-01-01 to 2023-05-31 across 22 salinity stations.
- Observed salinity after QC: 10120 station-days, equivalent to 36.89% of the full daily grid.
- One salinity row was marked invalid by physical QC and excluded from the target/input value.
- Short causal forward-fill for salinity inputs filled 3115 station-days. The target column remains observed-only.

## Multi-Source Coverage

- ERA5-Land daily weather rows: 27434 rows across 22 stations, with 0 station-days containing missing weather values after merging.
- ERA5 extraction buffer values in the processed dataset: 12000 m. This should be reported as buffered ERA5-Land extraction, not exact point sampling.
- Sentinel-2 previous-month composites: 902 rows across 22 stations and 41 target months (2020-01 to 2023-05).
- Missing Sentinel-2 target months relative to the daily grid: none.

## Salinity Coverage Notes

- Highest salinity observation coverage: XUAN_KHANH with 43.54% of station-days observed.
- Lowest salinity observation coverage: BINH_DAI with 21.01% of station-days observed.
- Highest monthly mean observed salinity: 2020-04, mean = 14.09, max = 29.20.

## Top Linear Associations

The following Pearson correlations are computed only on rows with observed salinity target values. They are descriptive EDA values, not model evidence:

- `wind_speed_10m_ms`: r = 0.535, n = 10120
- `soil_moisture_layer1_vol`: r = -0.423, n = 10120
- `wind_u_10m_ms`: r = -0.420, n = 10120
- `temperature_2m_min_c`: r = 0.252, n = 10120
- `s2_B11_mean`: r = -0.241, n = 9653
- `s2_SWIR1_mean`: r = -0.241, n = 9653
- `s2_MNDWI_mean`: r = 0.237, n = 9653
- `s2_R_1_mean`: r = -0.237, n = 9653
- `s2_B12_mean`: r = -0.235, n = 9653
- `s2_SWIR2_mean`: r = -0.235, n = 9653

## Files Generated

- `eda_overview_metrics.csv`: overall source and merged-dataset metrics.
- `eda_station_coverage.csv`: station-level salinity and Sentinel-2 coverage.
- `eda_monthly_coverage.csv`: month-level observation and weather summaries.
- `eda_feature_missingness.csv`: missingness by column.
- `eda_salinity_monthly_stats.csv`: station-month salinity statistics.
- `eda_feature_correlations.csv`: descriptive Pearson correlations with salinity max.
- SVG figures in this folder can be opened directly in a browser or inserted into the report.
