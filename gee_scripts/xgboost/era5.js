// ----------------------------------------------------------------------------
// 1) Station master: lon/lat converted from DMS to WGS84 decimal degrees.
// ----------------------------------------------------------------------------
var stations = ee.FeatureCollection([

  ee.Feature(ee.Geometry.Point([106.528900, 9.880839]), {
    station_id: 'BENTRAI',
    station_name: 'Bến Trại',
    river_name: 'Cổ Chiên',
    lon: 106.528900,
    lat: 9.880839
  }),

  ee.Feature(ee.Geometry.Point([105.605022, 9.976389]), {
    station_id: 'ANTHUAN',
    station_name: 'An Thuận',
    river_name: 'Hàm Luông',
    lon: 105.605022,
    lat: 9.976389
  }),

  ee.Feature(ee.Geometry.Point([106.705622, 10.204019]), {
    station_id: 'BINHDAI',
    station_name: 'Bình Đại',
    river_name: 'Cửa Đại',
    lon: 106.705622,
    lat: 10.204019
  }),

  ee.Feature(ee.Geometry.Point([106.400003, 10.138889]), {
    station_id: 'GIONGTROM',
    station_name: 'Giồng Trôm',
    river_name: 'Hàm Luông',
    lon: 106.400003,
    lat: 10.138889
  }),

  ee.Feature(ee.Geometry.Point([106.388889, 9.980556]), {
    station_id: 'HUONGMY',
    station_name: 'Hương Mỹ',
    river_name: 'Cổ Chiên',
    lon: 106.388889,
    lat: 9.980556
  }),

  ee.Feature(ee.Geometry.Point([106.265278, 10.091667]), {
    station_id: 'KHANHTHANHTAN',
    station_name: 'Khánh Thạnh Tân',
    river_name: 'Cổ Chiên',
    lon: 106.265278,
    lat: 10.091667
  }),

  ee.Feature(ee.Geometry.Point([106.583336, 10.243056]), {
    station_id: 'LOCTHUAN',
    station_name: 'Lộc Thuận',
    river_name: 'Cửa Đại',
    lon: 106.583336,
    lat: 10.243056
  }),

  ee.Feature(ee.Geometry.Point([106.348934, 10.222313]), {
    station_id: 'MYHOA',
    station_name: 'Mỹ Hóa',
    river_name: 'Hàm Luông',
    lon: 106.348934,
    lat: 10.222313
  }),

  // Nên xóa nếu không còn trong dữ liệu
  ee.Feature(ee.Geometry.Point([106.275000, 10.031500]), {
    station_id: 'SONDOC',
    station_name: 'Sơn Đốc',
    river_name: 'Hàm Luông',
    lon: 106.275000,
    lat: 10.031500
  }),

  ee.Feature(ee.Geometry.Point([105.088594, 9.346822]), {
    station_id: 'THOIBINH',
    station_name: 'Thới Bình',
    river_name: 'Chắc Băng',
    lon: 105.088594,
    lat: 9.346822
  }),

  ee.Feature(ee.Geometry.Point([105.123694, 9.871861]), {
    station_id: 'ANNINH',
    station_name: 'An Ninh',
    river_name: 'Cái Bé',
    lon: 105.123694,
    lat: 9.871861
  }),

  ee.Feature(ee.Geometry.Point([105.278861, 9.723144]), {
    station_id: 'GOQUAO',
    station_name: 'Gò Quao',
    river_name: 'Cái Lớn',
    lon: 105.278861,
    lat: 9.723144
  }),

  ee.Feature(ee.Geometry.Point([106.447583, 9.883454]), {
    station_id: 'XEORO',
    station_name: 'Xẻo Rô',
    river_name: 'Cái Lớn',
    lon: 106.447583,
    lat: 9.883454
  }),

  ee.Feature(ee.Geometry.Point([106.475430, 10.638366]), {
    station_id: 'BENLUC',
    station_name: 'Bến Lức',
    river_name: 'Vàm Cỏ Đông',
    lon: 106.475430,
    lat: 10.638366
  }),

  ee.Feature(ee.Geometry.Point([106.425759, 10.539013]), {
    station_id: 'TANAN',
    station_name: 'Tân An',
    river_name: 'Vàm Cỏ Tây',
    lon: 106.425759,
    lat: 10.539013
  }),

  ee.Feature(ee.Geometry.Point([106.583344, 10.477281]), {
    station_id: 'CAUNOI',
    station_name: 'Cầu Nổi',
    river_name: 'Vàm Cỏ',
    lon: 106.583344,
    lat: 10.477281
  }),

  ee.Feature(ee.Geometry.Point([106.191730, 10.658176]), {
    station_id: 'TUYENNHON',
    station_name: 'Tuyên Nhơn',
    river_name: 'Vàm Cỏ Tây',
    lon: 106.191730,
    lat: 10.658176
  }),

  ee.Feature(ee.Geometry.Point([106.402953, 10.790806]), {
    station_id: 'XUANKHANH',
    station_name: 'Xuân Khánh',
    river_name: 'Vàm Cỏ Đông',
    lon: 106.402953,
    lat: 10.790806
  }),

  ee.Feature(ee.Geometry.Point([105.997167, 9.833361]), {
    station_id: 'ANLACTAY',
    station_name: 'An Lạc Tây',
    river_name: 'Hậu',
    lon: 105.997167,
    lat: 9.833361
  }),

  ee.Feature(ee.Geometry.Point([106.074472, 9.734864]), {
    station_id: 'DAINGAI',
    station_name: 'Đại Ngãi',
    river_name: 'Hậu',
    lon: 106.074472,
    lat: 9.734864
  }),

  ee.Feature(ee.Geometry.Point([106.137108, 9.632258]), {
    station_id: 'LONGPHU',
    station_name: 'Long Phú',
    river_name: 'Hậu',
    lon: 106.137108,
    lat: 9.632258
  }),

  ee.Feature(ee.Geometry.Point([106.017856, 9.597708]), {
    station_id: 'SOCTRANG',
    station_name: 'Sóc Trăng',
    river_name: 'Kênh Mespro',
    lon: 106.017856,
    lat: 9.597708
  }),

  ee.Feature(ee.Geometry.Point([105.851417, 9.503667]), {
    station_id: 'THANHPHU',
    station_name: 'Thạnh Phú',
    river_name: 'Kênh Nhu Gia',
    lon: 105.851417,
    lat: 9.503667
  }),

  ee.Feature(ee.Geometry.Point([106.201456, 9.528211]), {
    station_id: 'TRANDE',
    station_name: 'Trần Đề',
    river_name: 'Hậu',
    lon: 106.201456,
    lat: 9.528211
  }),

  ee.Feature(ee.Geometry.Point([106.737017, 10.273983]), {
    station_id: 'VAMKENH',
    station_name: 'Vàm Kênh',
    river_name: 'Cửa Tiểu',
    lon: 106.737017,
    lat: 10.273983
  }),

  ee.Feature(ee.Geometry.Point([106.428417, 10.311028]), {
    station_id: 'ANDINH',
    station_name: 'An Định',
    river_name: 'Tiền',
    lon: 106.428417,
    lat: 10.311028
  }),

  ee.Feature(ee.Geometry.Point([106.592389, 10.290253]), {
    station_id: 'HOABINH',
    station_name: 'Hòa Bình',
    river_name: 'Cửa Tiểu',
    lon: 106.592389,
    lat: 10.290253
  }),

  ee.Feature(ee.Geometry.Point([106.354472, 9.975806]), {
    station_id: 'TRAVINH',
    station_name: 'Trà Vinh',
    river_name: 'Cổ Chiên',
    lon: 106.354472,
    lat: 9.975806
  }),

  ee.Feature(ee.Geometry.Point([106.114142, 9.758450]), {
    station_id: 'CAUQUAN',
    station_name: 'Cầu Quan',
    river_name: 'Hậu',
    lon: 106.114142,
    lat: 9.758450
  }),

  ee.Feature(ee.Geometry.Point([106.447750, 9.883374]), {
    station_id: 'HUNGMY',
    station_name: 'Hưng Mỹ',
    river_name: 'Cổ Chiên',
    lon: 106.447750,
    lat: 9.883374
  }),

  ee.Feature(ee.Geometry.Point([106.243158, 9.614764]), {
    station_id: 'TRAKHA',
    station_name: 'Trà Kha',
    river_name: 'Hậu',
    lon: 106.243158,
    lat: 9.614764
  }),

  ee.Feature(ee.Geometry.Point([106.307139, 9.996667]), {
    station_id: 'LANGTHE',
    station_name: 'Láng Thé',
    river_name: null,
    lon: 106.307139,
    lat: 9.996667
  }),

  ee.Feature(ee.Geometry.Point([106.249944, 10.062750]), {
    station_id: 'CAIHOP',
    station_name: 'Cái Hóp',
    river_name: null,
    lon: 106.249944,
    lat: 10.062750
  })

]);
// Change these two dates if your salinity file has a different period.
var startDate = '2020-01-01';
var endDateExclusive = '2023-06-01'; // filterDate end is exclusive

var era5ScaleMeters = 10000;

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
// 3) One row for each station × day.
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

  var sampled = image.sampleRegions({
    collection: stations,
    scale: era5ScaleMeters,
    geometries: false,
    tileScale: 4
  });

  return sampled.map(function(feature) {
    return feature.set({
      date: imageDate.format('YYYY-MM-dd'),
      year: imageDate.get('year'),
      month: imageDate.get('month'),
      day: imageDate.get('day'),
      day_of_year: imageDate.getRelative('day', 'year').add(1),
      source_dataset: 'ECMWF/ERA5_LAND/DAILY_AGGR'
    });
  });
})).flatten();

var exportSelectors = [
  'station_id', 'station_name', 'river_name', 'lon', 'lat',
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
'source_dataset'
];

records = records.sort('station_id').sort('date');

print('Expected rows (22 × number of days)', dailyWeather.size().multiply(stations.size()));
print('Actual rows', records.size());
print('Preview', records.limit(20));

Map.setCenter(106.25, 10.05, 8);
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