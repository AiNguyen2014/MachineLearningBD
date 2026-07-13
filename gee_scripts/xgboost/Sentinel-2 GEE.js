/**
 * ============================================================================
 * Sentinel-2 GEE — WEEKLY XGBOOST 30 STATIONS
 * ----------------------------------------------------------------------------
 * Mục tiêu:
 *   Trích phổ Sentinel-2 theo đúng 30 trạm trong new_weekly_data.csv
 *   để sau đó aggregate daily -> weekly và merge vào dataset XGBoost.
 *
 * Chạy từng năm:
 *   YEAR = 2020
 *   YEAR = 2021
 *   YEAR = 2022
 *   YEAR = 2023
 *
 * V5 gồm 9 strategy:
 *   Buffer: 20m / 30m / 50m
 *   Mask:
 *     MNDWI_basic  = MNDWI > 0 AND MNDWI > NDVI
 *     MNDWI_strict = MNDWI > 0 AND MNDWI > NDVI AND NDVI < 0.2
 *     NDWI_basic   = NDWI > 0 AND NDVI < 0.2
 *
 * Feature groups:
 *   Core:
 *     B2, B3, B4, B5, B8, B11, B12,
 *     MNDWI, NDWI, NDVI, NDTI, NDCI, Red_SWIR1, Red_SWIR2
 *
 *   From reference paper:
 *     BGRratio, R1_Blue_Red, R2_Blue_NIR,
 *     R3_Green_Red, R4_Green_NIR, BI
 *
 *   Candidate / ablation:
 *     SI1, SI2, SI3
 * ============================================================================
 */

// =======================
// 0. CONFIG
// =======================

var YEAR = 2023;  // <<< ĐỔI 2020 / 2021 / 2022 / 2023

// Nếu ALLBUF quá nặng, chạy tách:
// var BUFFERS = [20]; var RUN_TAG = 'BUF20';
// var BUFFERS = [30]; var RUN_TAG = 'BUF30';
// var BUFFERS = [50]; var RUN_TAG = 'BUF50';
var BUFFERS = [20, 30, 50];
var RUN_TAG = 'ALLBUF';

var SCALE = 10;
var CLOUD_PROB_MAX = 40;
var CLOUDY_TILE_MAX = 80;
var MNDWI_MIN = 0.0;
var NDWI_MIN = 0.0;
var NDVI_MAX = 0.20;
var EPS = 1e-6;

// Giữ rộng, lọc chặt ở Python sau.
// Nếu để 0 thì có thể xuất nhiều dòng không có nước; 1 là hợp lý.
var MIN_EXPORT_WATER_PX = 1;

// Lấy mùa khô + tháng 6 vì weekly data kéo tới đầu tháng 6.
var START = ee.Date.fromYMD(YEAR - 1, 12, 1);
var END   = ee.Date.fromYMD(YEAR, 7, 1);

// =======================
// 1. STATIONS — 30 TRẠM TỪ new_weekly_data.csv
// =======================

var stations = ee.FeatureCollection([
  ee.Feature(ee.Geometry.Point([106.428417, 10.311028]), {station_id: 'ANDINH'}),
  ee.Feature(ee.Geometry.Point([105.997167,  9.833361]), {station_id: 'ANLACTAY'}),
  ee.Feature(ee.Geometry.Point([105.123694,  9.871861]), {station_id: 'ANNINH'}),
  ee.Feature(ee.Geometry.Point([106.605022,  9.976389]), {station_id: 'ANTHUAN'}),
  ee.Feature(ee.Geometry.Point([106.475430, 10.638366]), {station_id: 'BENLUC'}),
  ee.Feature(ee.Geometry.Point([106.528900,  9.880839]), {station_id: 'BENTRAI'}),
  ee.Feature(ee.Geometry.Point([106.249944, 10.062750]), {station_id: 'CAIHOP'}),
  ee.Feature(ee.Geometry.Point([106.583344, 10.477281]), {station_id: 'CAUNOI'}),
  ee.Feature(ee.Geometry.Point([106.114142,  9.758450]), {station_id: 'CAUQUAN'}),
  ee.Feature(ee.Geometry.Point([106.074472,  9.734864]), {station_id: 'DAINGAI'}),
  ee.Feature(ee.Geometry.Point([106.400003, 10.138889]), {station_id: 'GIONGTROM'}),
  ee.Feature(ee.Geometry.Point([105.278861,  9.723144]), {station_id: 'GOQUAO'}),
  ee.Feature(ee.Geometry.Point([106.592389, 10.290253]), {station_id: 'HOABINH'}),
  ee.Feature(ee.Geometry.Point([106.447750,  9.883374]), {station_id: 'HUNGMY'}),
  ee.Feature(ee.Geometry.Point([106.388889,  9.980556]), {station_id: 'HUONGMY'}),
  ee.Feature(ee.Geometry.Point([106.265278, 10.091667]), {station_id: 'KHANHTHANHTAN'}),
  ee.Feature(ee.Geometry.Point([106.307139,  9.996667]), {station_id: 'LANGTHE'}),
  ee.Feature(ee.Geometry.Point([106.6, 10.24305555]), {station_id: 'LOCTHUAN'}),
  ee.Feature(ee.Geometry.Point([106.137108,  9.632258]), {station_id: 'LONGPHU'}),
  ee.Feature(ee.Geometry.Point([106.348934, 10.222313]), {station_id: 'MYHOA'}),
  ee.Feature(ee.Geometry.Point([106.017856,  9.597708]), {station_id: 'SOCTRANG'}),
  ee.Feature(ee.Geometry.Point([106.425759, 10.539013]), {station_id: 'TANAN'}),
  ee.Feature(ee.Geometry.Point([105.851417,  9.503667]), {station_id: 'THANHPHU'}),
  ee.Feature(ee.Geometry.Point([105.088594,  9.346822]), {station_id: 'THOIBINH'}),
  ee.Feature(ee.Geometry.Point([106.243158,  9.614764]), {station_id: 'TRAKHA'}),
  ee.Feature(ee.Geometry.Point([106.201456,  9.528211]), {station_id: 'TRANDE'}),
  ee.Feature(ee.Geometry.Point([106.354472,  9.975806]), {station_id: 'TRAVINH'}),
  ee.Feature(ee.Geometry.Point([106.191730, 10.658176]), {station_id: 'TUYENNHON'}),
  ee.Feature(ee.Geometry.Point([106.447583,  9.883454]), {station_id: 'XEORO'}),
  ee.Feature(ee.Geometry.Point([106.402953, 10.790806]), {station_id: 'XUANKHANH'})
]);

// =======================
// 2. CLOUD MASK
// =======================

function filterDrySeason(col) {
  return col.filter(ee.Filter.or(
    ee.Filter.calendarRange(12, 12, 'month'),
    ee.Filter.calendarRange(1, 6, 'month')
  ));
}

function attachCloud(col) {
  var prob = ee.ImageCollection('COPERNICUS/S2_CLOUD_PROBABILITY')
    .filterDate(START, END);

  var join = ee.Join.saveFirst('s2cloudless');

  var cond = ee.Filter.equals({
    leftField: 'system:index',
    rightField: 'system:index'
  });

  return ee.ImageCollection(join.apply(col, prob, cond));
}

function maskClouds(img) {
  var cloudMask = ee.Image(img.get('s2cloudless'))
    .select('probability')
    .lt(CLOUD_PROB_MAX);

  var scl = img.select('SCL');

  var sclMask = scl.neq(0)
    .and(scl.neq(1))
    .and(scl.neq(3))
    .and(scl.neq(8))
    .and(scl.neq(9))
    .and(scl.neq(10))
    .and(scl.neq(11));

  var qa = img.select('QA60');

  var qaMask = qa.bitwiseAnd(1 << 10).eq(0)
    .and(qa.bitwiseAnd(1 << 11).eq(0));

  var edge = img.select('B8A').mask()
    .and(img.select('B9').mask());

  return img
    .updateMask(cloudMask)
    .updateMask(sclMask)
    .updateMask(qaMask)
    .updateMask(edge)
    .copyProperties(img, ['system:time_start', 'system:index']);
}

// =======================
// 3. FEATURE FUNCTIONS
// =======================

function nd(a, b, name) {
  return a.subtract(b)
    .divide(a.add(b).add(EPS))
    .rename(name);
}

function ratio(a, b, name) {
  return a.divide(b.add(EPS)).rename(name);
}

function safeSqrt(x, name) {
  return x.max(0).sqrt().rename(name);
}

function addIndicesAndMasks(img) {
  var sr = img.select(['B2','B3','B4','B5','B8','B11','B12'])
    .divide(10000)
    .toFloat();

  var B   = sr.select('B2');
  var G   = sr.select('B3');
  var R   = sr.select('B4');
  var RE1 = sr.select('B5');
  var NIR = sr.select('B8');
  var SW1 = sr.select('B11');
  var SW2 = sr.select('B12');

  // Core indices
  var mndwi = nd(G, SW1, 'MNDWI');
  var ndwi  = nd(G, NIR, 'NDWI');
  var ndvi  = nd(NIR, R, 'NDVI');

  var ndti = nd(R, G, 'NDTI');
  var ndci = nd(RE1, R, 'NDCI');

  var redSw1 = ratio(R, SW1, 'Red_SWIR1');
  var redSw2 = ratio(R, SW2, 'Red_SWIR2');

  // From reference paper / salinity-hazard mapping
  var bgrRatio = B.add(G).divide(R.add(EPS)).rename('BGRratio');

  var r1 = ratio(B, R, 'R1_Blue_Red');
  var r2 = ratio(B, NIR, 'R2_Blue_NIR');
  var r3 = ratio(G, R, 'R3_Green_Red');
  var r4 = ratio(G, NIR, 'R4_Green_NIR');

  var bi = safeSqrt(G.pow(2).add(NIR.pow(2)), 'BI');

  // Candidate / ablation indices
  var si1 = safeSqrt(B.multiply(R), 'SI1');
  var si2 = safeSqrt(G.multiply(R), 'SI2');
  var si3 = safeSqrt(G.pow(2).add(R.pow(2)).add(NIR.pow(2)), 'SI3');

  // Water masks
  var waterMndwiBasic = mndwi.gt(MNDWI_MIN)
    .and(mndwi.gt(ndvi))
    .rename('water_MNDWI_basic');

  var waterMndwiStrict = mndwi.gt(MNDWI_MIN)
    .and(mndwi.gt(ndvi))
    .and(ndvi.lt(NDVI_MAX))
    .rename('water_MNDWI_strict');

  var waterNdwiBasic = ndwi.gt(NDWI_MIN)
    .and(ndvi.lt(NDVI_MAX))
    .rename('water_NDWI_basic');

  var raw = ee.Image.cat([
    B.rename('B2'),
    G.rename('B3'),
    R.rename('B4'),
    RE1.rename('B5'),
    NIR.rename('B8'),
    SW1.rename('B11'),
    SW2.rename('B12')
  ]);

  return raw
    .addBands([
      mndwi, ndwi, ndvi,
      ndti, ndci,
      redSw1, redSw2,
      bgrRatio,
      r1, r2, r3, r4,
      bi,
      si1, si2, si3,
      waterMndwiBasic,
      waterMndwiStrict,
      waterNdwiBasic
    ])
    .copyProperties(img, ['system:time_start', 'system:index']);
}

var FEATURE_BANDS = [
  // Raw bands
  'B2','B3','B4','B5','B8','B11','B12',

  // Core
  'MNDWI','NDWI','NDVI',
  'NDTI','NDCI',
  'Red_SWIR1','Red_SWIR2',

  // From paper
  'BGRratio',
  'R1_Blue_Red',
  'R2_Blue_NIR',
  'R3_Green_Red',
  'R4_Green_NIR',
  'BI',

  // Candidate / ablation
  'SI1','SI2','SI3'
];

// =======================
// 4. COLLECTION
// =======================

var base = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterDate(START, END)
  .filterBounds(stations.geometry())
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', CLOUDY_TILE_MAX));

base = filterDrySeason(base);

var col = attachCloud(base)
  .filter(ee.Filter.notNull(['s2cloudless']))
  .map(maskClouds)
  .map(addIndicesAndMasks);

// =======================
// 5. EXTRACT STRATEGIES
// =======================

var MASK_TYPES = [
  'MNDWI_basic',
  'MNDWI_strict',
  'NDWI_basic'
];

var REDUCER = ee.Reducer.median()
  .combine({
    reducer2: ee.Reducer.count(),
    sharedInputs: true
  });

function extractStrategy(buf, maskName) {
  buf = ee.Number(buf);
  maskName = ee.String(maskName);

  var strategyId = ee.String('BUF')
    .cat(buf.format('%d'))
    .cat('_')
    .cat(maskName);

  var waterBand = ee.String('water_').cat(maskName);

  var stationBuffers = stations.map(function(f) {
    return ee.Feature(f)
      .buffer(buf)
      .copyProperties(f);
  });

  var perImage = col.map(function(img) {
    img = ee.Image(img);

    var waterMask = img.select([waterBand]);

    var waterFeat = img
      .updateMask(waterMask)
      .select(FEATURE_BANDS);

    var clearPx = img.select('B4').rename('clear_px');
    var geomPx = ee.Image.constant(1).rename('geom_px').toFloat();

    var outImg = waterFeat
      .addBands(clearPx)
      .addBands(geomPx);

    var date = img.date().format('YYYY-MM-dd');

    var fc = outImg.reduceRegions({
      collection: stationBuffers,
      reducer: REDUCER,
      scale: SCALE,
      tileScale: 4
    });

    return fc.map(function(f) {
      var nWater = ee.Number(f.get('B4_count'));
      var nClear = ee.Number(f.get('clear_px_count'));
      var nGeom  = ee.Number(f.get('geom_px_count'));

      return f.setGeometry(null).set({
        'date': date,
        'img_id': img.get('system:index'),
        'year': YEAR,
        'strategy_id': strategyId,
        'buffer_m': buf,
        'mask_type': maskName,
        'n_water_px': nWater,
        'n_clear_px': nClear,
        'n_geom_px': nGeom,
        'water_frac_clear': nWater.divide(nClear.max(1)),
        'water_frac_geom': nWater.divide(nGeom.max(1))
      });
    });
  }).flatten();

  return perImage.filter(ee.Filter.gte('n_water_px', MIN_EXPORT_WATER_PX));
}

// Create list of FeatureCollections for each buffer × mask
var strategyCollections = ee.List(BUFFERS).map(function(buf) {
  return ee.List(MASK_TYPES).map(function(maskName) {
    return extractStrategy(buf, maskName);
  });
}).flatten();

// Merge FeatureCollections
var table = ee.FeatureCollection(
  strategyCollections.iterate(function(fc, acc) {
    return ee.FeatureCollection(acc).merge(ee.FeatureCollection(fc));
  }, ee.FeatureCollection([]))
);

// =======================
// 6. EXPORT
// =======================

var idCols = [
  'station_id',
  'date',
  'year',
  'img_id',
  'strategy_id',
  'buffer_m',
  'mask_type',
  'n_water_px',
  'n_clear_px',
  'n_geom_px',
  'water_frac_clear',
  'water_frac_geom'
];

var medianCols = FEATURE_BANDS.map(function(b) {
  return b + '_median';
});

var countCols = FEATURE_BANDS.map(function(b) {
  return b + '_count';
});

var selectors = idCols
  .concat(medianCols)
  .concat(countCols)
  .concat([
    'clear_px_count',
    'geom_px_count'
  ]);

// Nếu bị User memory limit exceeded, comment các dòng print/map này.
// print('YEAR', YEAR, 'RUN_TAG', RUN_TAG, 'rows:', table.size());
// print('Preview:', table.limit(5));

Map.centerObject(stations, 9);
Map.addLayer(stations, {color: 'red'}, '30 weekly stations');

Export.table.toDrive({
  collection: table,
  description: 'S2_v5_weekly30_' + YEAR + '_' + RUN_TAG,
  fileNamePrefix: 'S2_v5_weekly30_' + YEAR + '_' + RUN_TAG,
  fileFormat: 'CSV',
  selectors: selectors
});