// Sentinel-2 previous-month composite extraction for salinity stations.
// Copy this script into the Google Earth Engine Code Editor.
//
// Output grain:
//   one row per station_id x target month.
//   For every target month, spectral features are computed from the previous
//   calendar month's cloud-masked Sentinel-2 median composite.
//
// Example:
//   target_year=2021, target_month=3 uses Sentinel-2 images from
//   2021-02-01 inclusive to 2021-03-01 exclusive.

// ---------------------------------------------------------------------------
// 1. Settings
// ---------------------------------------------------------------------------

var TARGET_START = ee.Date('2020-01-01');
var TARGET_END_INCLUSIVE = ee.Date('2023-05-01'); // last target month to export
var BUFFER_METERS = 50;
var CLOUD_PROB_THRESHOLD = 40;
var SCALE_METERS = 10;

// ---------------------------------------------------------------------------
// 2. Stations
// ---------------------------------------------------------------------------

var stationRows = [
  ['AN_THUAN', 9.97638888888889, 106.60502222222222],
  ['BEN_LUC', 10.638366, 106.475430],
  ['BEN_TRAI', 9.880838888888889, 106.5289],
  ['BINH_DAI', 10.20401944, 106.70562222],
  ['CAU_NOI', 10.477280555555556, 106.58334444444444],
  ['CAU_QUAN', 9.75845, 106.11414166666664],
  ['DAI_NGAI', 9.734863888888889, 106.0744722222222],
  ['GO_QUAO', 9.723144444444443, 105.27886111111113],
  ['HOA_BINH', 10.290253, 106.592389],
  ['HUNG_MY', 9.883374, 106.447750],
  ['HUONG_MY', 9.980555555555556, 106.3888888888889],
  ['LOC_THUAN', 10.243055555555555, 106.6],
  ['MY_HOA', 10.222313, 106.348934],
  // SON_DOC was not present in New_Coor.csv, so this keeps the old coordinate.
  ['SON_DOC', 10.054167, 106.463889],
  ['TAN_AN', 10.539013, 106.425759],
  ['TRAN_DE', 9.528211111111112, 106.20145555555555],
  ['TRA_KHA', 9.614763888888888, 106.24315833333334],
  ['TRA_VINH', 9.975806, 106.354472],
  ['TUYEN_NHON', 10.658176, 106.191730],
  ['VAM_KENH', 10.273983, 106.737017],
  // Please re-check XEO_RO if needed; this uses New_Coor.csv.
  ['XEO_RO', 9.883454, 106.4475831],
  ['XUAN_KHANH', 10.790805555555556, 106.40295277777778]
];

var stations = ee.FeatureCollection(stationRows.map(function(row) {
  var stationId = row[0];
  var lat = row[1];
  var lon = row[2];
  return ee.Feature(ee.Geometry.Point([lon, lat]).buffer(BUFFER_METERS), {
    station_id: stationId,
    lat: lat,
    lon: lon
  });
}));

Map.centerObject(stations, 8);
Map.addLayer(stations, {color: 'red'}, 'station buffers');

// ---------------------------------------------------------------------------
// 3. Sentinel-2 cloud masking and spectral indices
// ---------------------------------------------------------------------------

function maskS2Clouds(image) {
  var cloudProb = ee.Image(image.get('s2cloudless')).select('probability');
  var qa = image.select('QA60');
  var scl = image.select('SCL');

  var cloudBitMask = 1 << 10;
  var cirrusBitMask = 1 << 11;

  var qaMask = qa.bitwiseAnd(cloudBitMask).eq(0)
    .and(qa.bitwiseAnd(cirrusBitMask).eq(0));
  var cloudProbMask = cloudProb.lt(CLOUD_PROB_THRESHOLD);
  var sclMask = scl.neq(3)   // cloud shadow
    .and(scl.neq(8))         // medium probability cloud
    .and(scl.neq(9))         // high probability cloud
    .and(scl.neq(10))        // thin cirrus
    .and(scl.neq(11));       // snow/ice

  return image
    .updateMask(qaMask)
    .updateMask(cloudProbMask)
    .updateMask(sclMask)
    .select(['B2', 'B3', 'B4', 'B8', 'B11', 'B12'])
    .divide(10000)
    .copyProperties(image, image.propertyNames());
}

function addIndices(image) {
  var blue = image.select('B2');
  var green = image.select('B3');
  var red = image.select('B4');
  var nir = image.select('B8');
  var swir1 = image.select('B11');
  var swir2 = image.select('B12');

  var ndvi = nir.subtract(red).divide(nir.add(red)).rename('NDVI');
  var ndwi = green.subtract(nir).divide(green.add(nir)).rename('NDWI');
  var mndwi = green.subtract(swir1).divide(green.add(swir1)).rename('MNDWI');
  var evi = nir.subtract(red).multiply(2.5)
    .divide(nir.add(red.multiply(6)).subtract(blue.multiply(7.5)).add(1))
    .rename('EVI');
  var savi = nir.subtract(red).multiply(1.5)
    .divide(nir.add(red).add(0.5))
    .rename('SAVI');
  var rvi = nir.divide(red).rename('RVI');
  var bi = green.pow(2).add(nir.pow(2)).sqrt().rename('BI');

  // Indices emphasized/listed in the paper.
  var bgrRatio = blue.add(green).divide(red).rename('BGRratio');
  var si1 = green.multiply(red).sqrt().rename('SI_1');
  var si2 = green.pow(2).add(red.pow(2)).sqrt().rename('SI_2');
  var si3 = green.pow(2).add(red.pow(2)).add(nir.pow(2)).sqrt().rename('SI_3');
  var r1 = blue.divide(red).rename('R_1');
  var r2 = blue.divide(nir).rename('R_2');
  var r3 = green.divide(red).rename('R_3');
  var r4 = green.divide(nir).rename('R_4');

  // Extra water/SWIR descriptors that are often useful for masking/context.
  var redSwir1 = red.divide(swir1).rename('Red_SWIR1_ratio');
  var vv = ee.Image.cat([
    ndvi, ndwi, mndwi, evi, savi, rvi, bi,
    bgrRatio, si1, si2, si3, r1, r2, r3, r4,
    redSwir1,
    swir1.rename('SWIR1'),
    swir2.rename('SWIR2')
  ]);

  return image.addBands(vv);
}

function getS2Collection(startDate, endDate) {
  var sr = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterBounds(stations.geometry())
    .filterDate(startDate, endDate);

  var clouds = ee.ImageCollection('COPERNICUS/S2_CLOUD_PROBABILITY')
    .filterBounds(stations.geometry())
    .filterDate(startDate, endDate);

  var joined = ee.ImageCollection(ee.Join.saveFirst('s2cloudless').apply({
    primary: sr,
    secondary: clouds,
    condition: ee.Filter.equals({
      leftField: 'system:index',
      rightField: 'system:index'
    })
  }));

  return joined.map(maskS2Clouds).map(addIndices);
}

// ---------------------------------------------------------------------------
// 4. Build previous-month station table
// ---------------------------------------------------------------------------

var nMonths = TARGET_END_INCLUSIVE.difference(TARGET_START, 'month').add(1);
var targetMonths = ee.List.sequence(0, nMonths.subtract(1)).map(function(n) {
  return TARGET_START.advance(ee.Number(n), 'month');
});

function extractPreviousMonthForTarget(targetMonthStart) {
  targetMonthStart = ee.Date(targetMonthStart);
  var previousStart = targetMonthStart.advance(-1, 'month');
  var previousEnd = targetMonthStart;

  var collection = getS2Collection(previousStart, previousEnd);
  var validImageCount = collection.size();

  var composite = collection.median();

  var reducer = ee.Reducer.mean()
    .combine({reducer2: ee.Reducer.stdDev(), sharedInputs: true})
    .combine({reducer2: ee.Reducer.count(), sharedInputs: true});

  var rows = composite.reduceRegions({
    collection: stations,
    reducer: reducer,
    scale: SCALE_METERS,
    tileScale: 4
  });

  return rows.map(function(feature) {
    return feature.set({
      target_ym: targetMonthStart.format('YYYY-MM'),
      target_year: targetMonthStart.get('year'),
      target_month: targetMonthStart.get('month'),
      s2_prev_start: previousStart.format('YYYY-MM-dd'),
      s2_prev_end_exclusive: previousEnd.format('YYYY-MM-dd'),
      s2_valid_image_count: validImageCount,
      buffer_m: BUFFER_METERS,
      cloud_prob_threshold: CLOUD_PROB_THRESHOLD
    });
  });
}

var output = ee.FeatureCollection(targetMonths.map(extractPreviousMonthForTarget)).flatten();

print('Target month count', nMonths);
print('Target months', targetMonths.map(function(d) {
  return ee.Date(d).format('YYYY-MM');
}));
print('Output preview', output.limit(10));
print('Row count', output.size());
print('Rows by target year-month', output.aggregate_histogram('target_ym'));
print('Rows by station', output.aggregate_histogram('station_id'));

// Optional visual check for one target month. This displays previous-month
// composite for March 2021, i.e. February 2021 imagery.
var previewTarget = ee.Date('2021-03-01');
var previewComposite = getS2Collection(previewTarget.advance(-1, 'month'), previewTarget).median();
Map.addLayer(previewComposite, {bands: ['B4', 'B3', 'B2'], min: 0, max: 0.25}, 'S2 previous-month RGB preview');
Map.addLayer(previewComposite.select('BGRratio'), {min: 1, max: 6, palette: ['blue', 'cyan', 'yellow', 'red']}, 'BGRratio preview');

// ---------------------------------------------------------------------------
// 5. Export
// ---------------------------------------------------------------------------

Export.table.toDrive({
  collection: output,
  description: 's2_previous_month_station_composites_2020_2023',
  fileNamePrefix: 's2_previous_month_station_composites_2020_2023',
  fileFormat: 'CSV',
  selectors: [
    'station_id', 'lat', 'lon',
    'target_ym', 'target_year', 'target_month',
    's2_prev_start', 's2_prev_end_exclusive', 's2_valid_image_count',
    'buffer_m', 'cloud_prob_threshold',
    'B2_mean', 'B2_stdDev', 'B2_count',
    'B3_mean', 'B3_stdDev', 'B3_count',
    'B4_mean', 'B4_stdDev', 'B4_count',
    'B8_mean', 'B8_stdDev', 'B8_count',
    'B11_mean', 'B11_stdDev', 'B11_count',
    'B12_mean', 'B12_stdDev', 'B12_count',
    'NDVI_mean', 'NDVI_stdDev', 'NDVI_count',
    'NDWI_mean', 'NDWI_stdDev', 'NDWI_count',
    'MNDWI_mean', 'MNDWI_stdDev', 'MNDWI_count',
    'EVI_mean', 'EVI_stdDev', 'EVI_count',
    'SAVI_mean', 'SAVI_stdDev', 'SAVI_count',
    'RVI_mean', 'RVI_stdDev', 'RVI_count',
    'BI_mean', 'BI_stdDev', 'BI_count',
    'BGRratio_mean', 'BGRratio_stdDev', 'BGRratio_count',
    'SI_1_mean', 'SI_1_stdDev', 'SI_1_count',
    'SI_2_mean', 'SI_2_stdDev', 'SI_2_count',
    'SI_3_mean', 'SI_3_stdDev', 'SI_3_count',
    'R_1_mean', 'R_1_stdDev', 'R_1_count',
    'R_2_mean', 'R_2_stdDev', 'R_2_count',
    'R_3_mean', 'R_3_stdDev', 'R_3_count',
    'R_4_mean', 'R_4_stdDev', 'R_4_count',
    'Red_SWIR1_ratio_mean', 'Red_SWIR1_ratio_stdDev', 'Red_SWIR1_ratio_count',
    'SWIR1_mean', 'SWIR1_stdDev', 'SWIR1_count',
    'SWIR2_mean', 'SWIR2_stdDev', 'SWIR2_count'
  ]
});
