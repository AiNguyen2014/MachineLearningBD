// Asset-free export of map-ready covariates for one week or month.
// ROI, a regular prediction grid, and river distance are created from public data.
// This lightweight version avoids vector closest-point and per-feature buffers.

var provinceNames = [
  'An Giang', 'Bac Lieu', 'Ben Tre', 'Ca Mau', 'Can Tho', 'Dong Thap',
  'Hau Giang', 'Kien Giang', 'Long An', 'Soc Trang', 'Tien Giang',
  'Tra Vinh', 'Vinh Long'
];
var provinces = ee.FeatureCollection('FAO/GAUL_SIMPLIFIED_500m/2015/level1')
  .filter(ee.Filter.eq('ADM0_NAME', 'Viet Nam'))
  .filter(ee.Filter.inList('ADM1_NAME', provinceNames));
var region = provinces.geometry();

var riverLines = ee.FeatureCollection('WWF/HydroSHEDS/v1/FreeFlowingRivers')
  .filterBounds(region.buffer(20000));

var gridSpacing = 5000; // Metres. Keep 5000 for the inexpensive baseline export.
var gridProjection = ee.Projection('EPSG:32648').atScale(gridSpacing);
var points = ee.Image.pixelCoordinates(gridProjection).sample({
  region: region,
  projection: gridProjection,
  scale: gridSpacing,
  geometries: true,
  tileScale: 4
}).map(function(feature) {
  var coordinates = feature.geometry().coordinates();
  return feature.set({
    grid_id: ee.String('g_').cat(ee.Number(feature.get('x')).round().toInt64().format('%d'))
      .cat('_').cat(ee.Number(feature.get('y')).round().toInt64().format('%d')),
    lon_first: coordinates.get(0),
    lat_first: coordinates.get(1)
  });
});

var start = ee.Date('2023-03-01');
var end = ee.Date('2023-04-01'); // End is exclusive. Use +7 days for a weekly export.
var exportName = 'mekong_covariates_2023_03_monthly';

function maskS2(image) {
  var scl = image.select('SCL');
  var clear = scl.neq(3).and(scl.neq(8)).and(scl.neq(9))
    .and(scl.neq(10)).and(scl.neq(11));
  return image.updateMask(clear).divide(10000)
    .copyProperties(image, ['system:time_start']);
}

function addSpectral(image) {
  var green = image.select('B3');
  var red = image.select('B4');
  var nir = image.select('B8');
  var swir1 = image.select('B11');
  var swir2 = image.select('B12');
  var eps = ee.Image.constant(1e-6);
  return image.addBands([
    green.subtract(swir1).divide(green.add(swir1).add(eps)).rename('MNDWI_median_week'),
    green.subtract(nir).divide(green.add(nir).add(eps)).rename('NDWI_median_week'),
    nir.subtract(red).divide(nir.add(red).add(eps)).rename('NDVI_median_week'),
    swir1.rename('B11_median_week'),
    swir2.rename('B12_median_week'),
    red.divide(swir1.add(eps)).rename('Red_SWIR1_median_week'),
    red.divide(swir2.add(eps)).rename('Red_SWIR2_median_week'),
    image.select('B2').add(green).divide(red.add(eps)).rename('BGRratio_median_week'),
    red.subtract(image.select('B2')).divide(red.add(image.select('B2')).add(eps))
      .rename('NDCI_median_week')
  ]);
}

var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(region).filterDate(start, end).map(maskS2).map(addSpectral);
var spectralNames = [
  'MNDWI_median_week', 'NDWI_median_week', 'NDVI_median_week',
  'B11_median_week', 'B12_median_week', 'Red_SWIR1_median_week',
  'Red_SWIR2_median_week', 'BGRratio_median_week', 'NDCI_median_week'
];
var spectral = s2.select(spectralNames).median();

var era = ee.ImageCollection('ECMWF/ERA5_LAND/DAILY_AGGR')
  .filterBounds(region).filterDate(start, end);
var weather = ee.Image.cat([
  era.select('temperature_2m').mean().subtract(273.15).rename('temperature_2m_c_mean'),
  era.select('total_precipitation_sum').sum().multiply(1000).rename('precipitation_mm_sum'),
  // ERA5-Land evaporation is an upward (negative) flux; train data uses magnitude.
  era.select('potential_evaporation_sum').sum().multiply(-1000)
    .rename('potential_evaporation_mm_sum'),
  era.select('runoff_sum').sum().multiply(1000).rename('runoff_mm_sum'),
  era.select('runoff_sum').max().multiply(1000).rename('runoff_mm_max'),
  era.select('surface_pressure').min().divide(100).rename('surface_pressure_hpa_min'),
  era.select('volumetric_soil_water_layer_1').mean().rename('soil_moisture_layer1_vol_mean'),
  era.select('surface_solar_radiation_downwards_sum').sum().divide(1e6)
    .rename('solar_radiation_mj_m2_sum')
]);

var dem = ee.Image('NASA/NASADEM_HGT/001').select('elevation').rename('DEM_first');
// Raster distance is substantially cheaper than geometry.distance for every grid point.
// At 500 m and a 256-pixel search radius, distances up to about 128 km are represented.
var riverScale = 500;
var riverProjection = ee.Projection('EPSG:32648').atScale(riverScale);
var riverRaster = ee.Image(0).byte().paint(riverLines, 1).reproject(riverProjection);
var riverDistance = riverRaster.fastDistanceTransform(256, 'pixels', 'squared_euclidean')
  .sqrt().multiply(riverScale).rename('Distance_to_River_first');
var covariates = spectral.addBands(weather).addBands(dem).addBands(riverDistance);
var s2Count = s2.select('B11_median_week').count().rename('s2_obs_count');
covariates = covariates.addBands(s2Count).addBands(s2Count.gt(0).rename('s2_available'));

var withStatic = points.map(function(feature) {
  return feature.set({
    period_start: start.format('YYYY-MM-dd'),
    period_end: end.format('YYYY-MM-dd')
  });
});

var sampled = covariates.reduceRegions({
  collection: withStatic,
  reducer: ee.Reducer.first(),
  scale: 20,
  tileScale: 4
});

// Keep only water-like spectral signatures, matching the salinity stations.
sampled = sampled
  .filter(ee.Filter.gt('MNDWI_median_week', 0))
  .filter(ee.Filter.lt('NDVI_median_week', 0))
  .filter(ee.Filter.lte('Distance_to_River_first', 5000));

Export.table.toDrive({
  collection: sampled,
  description: exportName,
  fileNamePrefix: exportName,
  fileFormat: 'CSV'
});

print('Selected provinces', provinces.aggregate_array('ADM1_NAME'));
print('Prediction point count', points.size());
Map.centerObject(region, 7);
Map.addLayer(provinces, {color: '202020'}, 'Mekong Delta ROI');
Map.addLayer(riverLines, {color: '2b83ba'}, 'HydroSHEDS rivers');
Map.addLayer(points.limit(5000), {color: 'd7191c'}, 'Prediction grid sample');
