/******************************************************************************
Extract daily ERA5-Land weather data for the 22 LSTM salinity stations.

Output grain: one row per station per calendar day.
Date range: 2020-01-01 through 2023-05-31 (end date is exclusive: 2023-06-01).
Expected output: 22 stations x 1,247 days = 27,434 rows.

Dataset:
  ECMWF/ERA5_LAND/DAILY_AGGR
Official catalog:
  https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_DAILY_AGGR

Notes:
- This is climate reanalysis, NOT a river water-level dataset.
- Values are extracted with a small buffer because ERA5-Land is land-only. Some
  estuary/coastal station points can fall on masked water pixels if sampled as a
  single point, which silently drops that station from sampleRegions.
- `potential_evaporation_mm_signed` is retained for traceability.
  `potential_evaporation_mm` is its absolute magnitude and is the preferred feature.
******************************************************************************/

// ----------------------------------------------------------------------------
// 1) Station master.
//    Coordinates are from Data/salinity_with_updated_coords.csv.
//    SON_DOC keeps the previous coordinate because it was missing from New_Coor.csv.
//    XEO_RO uses New_Coor.csv; re-check if needed because it changed substantially.
// ----------------------------------------------------------------------------
var stations = ee.FeatureCollection([
  ee.Feature(ee.Geometry.Point([106.60502222222222, 9.97638888888889]), {station_id: 'AN_THUAN', station_name: 'An Thuận', lon: 106.60502222222222, lat: 9.97638888888889}),
  ee.Feature(ee.Geometry.Point([106.475430, 10.638366]), {station_id: 'BEN_LUC', station_name: 'Bến Lức', lon: 106.475430, lat: 10.638366}),
  ee.Feature(ee.Geometry.Point([106.5289, 9.880838888888889]), {station_id: 'BEN_TRAI', station_name: 'Bến Trại', lon: 106.5289, lat: 9.880838888888889}),
  ee.Feature(ee.Geometry.Point([106.70562222, 10.20401944]), {station_id: 'BINH_DAI', station_name: 'Bình Đại', lon: 106.70562222, lat: 10.20401944}),
  ee.Feature(ee.Geometry.Point([106.58334444444444, 10.477280555555556]), {station_id: 'CAU_NOI', station_name: 'Cầu Nổi', lon: 106.58334444444444, lat: 10.477280555555556}),
  ee.Feature(ee.Geometry.Point([106.11414166666664, 9.75845]), {station_id: 'CAU_QUAN', station_name: 'Cầu Quan', lon: 106.11414166666664, lat: 9.75845}),
  ee.Feature(ee.Geometry.Point([106.0744722222222, 9.734863888888889]), {station_id: 'DAI_NGAI', station_name: 'Đại Ngãi', lon: 106.0744722222222, lat: 9.734863888888889}),
  ee.Feature(ee.Geometry.Point([105.27886111111113, 9.723144444444443]), {station_id: 'GO_QUAO', station_name: 'Gò Quao', lon: 105.27886111111113, lat: 9.723144444444443}),
  ee.Feature(ee.Geometry.Point([106.592389, 10.290253]), {station_id: 'HOA_BINH', station_name: 'Hòa Bình', lon: 106.592389, lat: 10.290253}),
  ee.Feature(ee.Geometry.Point([106.447750, 9.883374]), {station_id: 'HUNG_MY', station_name: 'Hưng Mỹ', lon: 106.447750, lat: 9.883374}),
  ee.Feature(ee.Geometry.Point([106.3888888888889, 9.980555555555556]), {station_id: 'HUONG_MY', station_name: 'Hương Mỹ', lon: 106.3888888888889, lat: 9.980555555555556}),
  ee.Feature(ee.Geometry.Point([106.6, 10.243055555555555]), {station_id: 'LOC_THUAN', station_name: 'Lộc Thuận', lon: 106.6, lat: 10.243055555555555}),
  ee.Feature(ee.Geometry.Point([106.348934, 10.222313]), {station_id: 'MY_HOA', station_name: 'Mỹ Hóa', lon: 106.348934, lat: 10.222313}),
  ee.Feature(ee.Geometry.Point([106.463889, 10.054167]), {station_id: 'SON_DOC', station_name: 'Sơn Đốc', lon: 106.463889, lat: 10.054167}),
  ee.Feature(ee.Geometry.Point([106.425759, 10.539013]), {station_id: 'TAN_AN', station_name: 'Tân An', lon: 106.425759, lat: 10.539013}),
  ee.Feature(ee.Geometry.Point([106.20145555555555, 9.528211111111112]), {station_id: 'TRAN_DE', station_name: 'Trần Đề', lon: 106.20145555555555, lat: 9.528211111111112}),
  ee.Feature(ee.Geometry.Point([106.24315833333334, 9.614763888888888]), {station_id: 'TRA_KHA', station_name: 'Trà Kha', lon: 106.24315833333334, lat: 9.614763888888888}),
  ee.Feature(ee.Geometry.Point([106.354472, 9.975806]), {station_id: 'TRA_VINH', station_name: 'Trà Vinh', lon: 106.354472, lat: 9.975806}),
  ee.Feature(ee.Geometry.Point([106.191730, 10.658176]), {station_id: 'TUYEN_NHON', station_name: 'Tuyên Nhơn', lon: 106.191730, lat: 10.658176}),
  ee.Feature(ee.Geometry.Point([106.737017, 10.273983]), {station_id: 'VAM_KENH', station_name: 'Vàm Kênh', lon: 106.737017, lat: 10.273983}),
  ee.Feature(ee.Geometry.Point([106.4475831, 9.883454]), {station_id: 'XEO_RO', station_name: 'Xẻo Rô', lon: 106.4475831, lat: 9.883454}),
  ee.Feature(ee.Geometry.Point([106.40295277777778, 10.790805555555556]), {station_id: 'XUAN_KHANH', station_name: 'Xuân Khánh', lon: 106.40295277777778, lat: 10.790805555555556})
]);

var startDate = '2020-01-01';
var endDateExclusive = '2023-06-01'; // filterDate end is exclusive
var era5ScaleMeters = 11132;
var era5BufferMeters = 12000;

var era5Regions = stations.map(function(feature) {
  return ee.Feature(feature.geometry().buffer(era5BufferMeters), feature.toDictionary());
});

// ----------------------------------------------------------------------------
// 2) Prepare daily model-ready weather bands and convert units.
// ----------------------------------------------------------------------------
function prepareDailyWeather(image) {
  var temperatureMeanC = image.select('temperature_2m')
    .subtract(273.15)
    .rename('temperature_2m_c');

  var temperatureMinC = image.select('temperature_2m_min')
    .subtract(273.15)
    .rename('temperature_2m_min_c');

  var temperatureMaxC = image.select('temperature_2m_max')
    .subtract(273.15)
    .rename('temperature_2m_max_c');

  var dewpointC = image.select('dewpoint_temperature_2m')
    .subtract(273.15)
    .rename('dewpoint_temperature_2m_c');

  // Flow bands are in metres of water. Clamp occasional negative packing artifacts.
  var precipM = image.select('total_precipitation_sum');
  var precipitationMm = precipM.where(precipM.lt(0), 0)
    .multiply(1000)
    .rename('precipitation_mm');

  var runoffM = image.select('runoff_sum');
  var runoffMm = runoffM.where(runoffM.lt(0), 0)
    .multiply(1000)
    .rename('runoff_mm');

  // Preserve source sign and export a non-negative magnitude for modelling.
  var potentialEvapSignedMm = image.select('potential_evaporation_sum')
    .multiply(1000)
    .rename('potential_evaporation_mm_signed');

  var potentialEvapMm = potentialEvapSignedMm.abs()
    .rename('potential_evaporation_mm');

  var windU = image.select('u_component_of_wind_10m')
    .rename('wind_u_10m_ms');

  var windV = image.select('v_component_of_wind_10m')
    .rename('wind_v_10m_ms');

  var windSpeed = windU.pow(2).add(windV.pow(2)).sqrt()
    .rename('wind_speed_10m_ms');

  var pressureHpa = image.select('surface_pressure')
    .divide(100)
    .rename('surface_pressure_hpa');

  var soilMoistureL1 = image.select('volumetric_soil_water_layer_1')
    .rename('soil_moisture_layer1_vol');

  var solarRadiationMj = image.select('surface_solar_radiation_downwards_sum')
    .divide(1000000)
    .rename('solar_radiation_mj_m2');

  return ee.Image.cat([
    temperatureMeanC,
    temperatureMinC,
    temperatureMaxC,
    dewpointC,
    precipitationMm,
    potentialEvapMm,
    potentialEvapSignedMm,
    runoffMm,
    windU,
    windV,
    windSpeed,
    pressureHpa,
    soilMoistureL1,
    solarRadiationMj
  ]).copyProperties(image, ['system:time_start']);
}

// ----------------------------------------------------------------------------
// 3) One row for each station × day. No interpolation is done in GEE.
// ----------------------------------------------------------------------------
var dailyWeather = ee.ImageCollection('ECMWF/ERA5_LAND/DAILY_AGGR')
  .filterDate(startDate, endDateExclusive)
  .map(prepareDailyWeather)
  .sort('system:time_start');

print('Number of daily ERA5-Land images', dailyWeather.size());
print('Stations', stations);
print('First processed ERA5-Land image', dailyWeather.first());

var imageList = dailyWeather.toList(dailyWeather.size());
var indexList = ee.List.sequence(0, dailyWeather.size().subtract(1));

var records = ee.FeatureCollection(indexList.map(function(index) {
  var image = ee.Image(imageList.get(index));
  var imageDate = ee.Date(image.get('system:time_start'));

  var sampled = image.reduceRegions({
    collection: era5Regions,
    reducer: ee.Reducer.mean(),
    scale: era5ScaleMeters,
    tileScale: 4
  });

  return sampled.map(function(feature) {
    return feature.set({
      date: imageDate.format('YYYY-MM-dd'),
      year: imageDate.get('year'),
      month: imageDate.get('month'),
      day: imageDate.get('day'),
      day_of_year: imageDate.getRelative('day', 'year').add(1),
      era5_buffer_m: era5BufferMeters,
      source_dataset: 'ECMWF/ERA5_LAND/DAILY_AGGR'
    });
  });
})).flatten();

var exportSelectors = [
  'station_id', 'station_name', 'lon', 'lat',
  'date', 'year', 'month', 'day', 'day_of_year',
  'temperature_2m_c', 'temperature_2m_min_c', 'temperature_2m_max_c',
  'dewpoint_temperature_2m_c',
  'precipitation_mm',
  'potential_evaporation_mm', 'potential_evaporation_mm_signed',
  'runoff_mm',
  'wind_u_10m_ms', 'wind_v_10m_ms', 'wind_speed_10m_ms',
  'surface_pressure_hpa',
  'soil_moisture_layer1_vol',
  'solar_radiation_mj_m2',
  'era5_buffer_m',
  'source_dataset'
];

records = records.sort('station_id').sort('date');

print('Expected rows (22 x number of days)', dailyWeather.size().multiply(stations.size()));
print('Actual rows', records.size());
print('Rows by station', records.aggregate_histogram('station_id'));
print('Preview', records.limit(20));

Map.centerObject(stations, 8);
Map.addLayer(stations, {color: 'red'}, '22 salinity stations');

// ----------------------------------------------------------------------------
// 4) Run this task from the Tasks tab to create a CSV in Google Drive.
// ----------------------------------------------------------------------------
Export.table.toDrive({
  collection: records,
  description: 'era5_land_daily_22_salinity_stations_2020_2023',
  folder: 'gee_weather_exports',
  fileNamePrefix: 'era5_land_daily_22_salinity_stations_2020_2023',
  fileFormat: 'CSV',
  selectors: exportSelectors
});
