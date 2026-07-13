# XGBoost spatial salinity test

Folder này dùng để thử bài toán **ước lượng độ mặn theo không gian** bằng XGBoost.

Khác với nhánh LSTM temporal forecasting, thử nghiệm này mặc định:

- không dùng `station_id` làm feature;
- không dùng lịch sử mặn như `salinity_lag1`, `salinity_lag2`;
- xem độ mặn quan trắc chỉ là `label`;
- dùng biến không gian, mùa vụ, khí tượng và Sentinel-2 để dự đoán độ mặn tại trạm/vùng chưa đo.

## Input

- `data/weekly_ml_dataset_v2_leftjoin.csv`: dataset weekly do nhóm XGBoost tổng hợp.
- `notebooks/XGBoost_pipeline_v2_original.ipynb`: notebook gốc để đối chiếu.

## Cài dependency

Môi trường `.venv_lstm` hiện có `pandas`, `numpy`, `sklearn`, nhưng chưa có `xgboost`.

```bash
./.venv_lstm/bin/python -m pip install xgboost
```

Trên macOS có thể cần thêm OpenMP runtime:

```bash
brew install libomp
```

## Chạy test

Temporal test giống notebook gốc:

```bash
./.venv_lstm/bin/python experiments/xgboost_spatial/run_spatial_xgb.py \
  --split temporal
```

Spatial CV để kiểm tra trạm mới:

```bash
./.venv_lstm/bin/python experiments/xgboost_spatial/run_spatial_xgb.py \
  --split spatial-cv \
  --n-splits 5
```

Spatio-temporal CV khó hơn:

```bash
./.venv_lstm/bin/python experiments/xgboost_spatial/run_spatial_xgb.py \
  --split spatiotemporal-cv \
  --n-splits 5
```

So sánh monthly aggregation:

```bash
./.venv_lstm/bin/python experiments/xgboost_spatial/run_spatial_xgb.py \
  --time-unit monthly \
  --split spatial-cv \
  --n-splits 5
```

## Ý nghĩa các split

- `temporal`: train 2020-2021, validation 2022, test 2023 trên các trạm đã xuất hiện trong train.
- `spatial-cv`: giữ từng nhóm trạm ra khỏi train để kiểm tra khả năng dự đoán trạm chưa từng thấy.
- `spatiotemporal-cv`: train các trạm train trong 2020-2021, validation 2022, test các trạm holdout trong 2023.

Nếu `temporal` tốt nhưng `spatial-cv` hoặc `spatiotemporal-cv` R2 âm, mô hình chưa đủ khả năng ngoại suy không gian.

## Kết quả chạy thử ban đầu

Đã chạy với feature mặc định, tức là không dùng `station_id`, không dùng `salinity_lag1/2`, không dùng `source_format`, không dùng `completeness_pct`.

| Time unit | Split | R2 log trung bình | RMSE g/L | MAE g/L | Diễn giải |
|---|---|---:|---:|---:|---|
| weekly | temporal | 0.754 | 2.146 | 1.665 | Tốt khi test tương lai trên các trạm đã có trong train |
| weekly | spatial-cv | 0.173 | 5.237 | 3.859 | Yếu khi giữ trạm ra khỏi train |
| weekly | spatiotemporal-cv | -1.438 | 4.165 | 3.499 | Rất yếu cho trạm mới trong năm 2023 |
| monthly | temporal | 0.764 | 1.572 | 1.317 | Tốt hơn weekly ở temporal nhưng chỉ còn 60 mẫu test |
| monthly | spatial-cv | 0.310 | 5.077 | 3.746 | Nhỉnh hơn weekly một chút ở spatial CV |
| monthly | spatiotemporal-cv | -0.801 | 3.317 | 2.837 | Vẫn âm khi test trạm holdout trong 2023 |

Kết luận tạm thời: dataset/feature hiện tại có thể dự báo temporal khá ổn, nhưng chưa đủ để khẳng định khả năng dự đoán không gian ở trạm mới. Monthly aggregation giảm số mẫu mạnh nhưng làm phổ ổn định hơn, nên spatial CV có cải thiện nhẹ. Tuy vậy spatio-temporal CV vẫn âm, tức là bài toán dự đoán trạm mới trong năm mới vẫn chưa ổn.

Monthly mode aggregate trực tiếp từ weekly dataset: mỗi dòng là station-year-month; `salinity_max_mean` là trung bình các weekly mean trong tháng; phổ Sentinel-2 là median của các weekly composite. Mặc định một tháng reliable khi có ít nhất 2 tuần reliable (`--monthly-min-reliable-weeks 2`).

Kết quả tổng hợp nằm ở `outputs/weekly_monthly_comparison.csv`.

## Correlation diagnostics

Chạy:

```bash
./.venv_lstm/bin/python experiments/xgboost_spatial/analyze_correlations.py
```

Kết quả nằm trong `outputs/correlations/`.

Tóm tắt theo nhóm feature:

| Time unit | Feature group | Median abs Spearman với log salinity | Max abs Spearman |
|---|---|---:|---:|
| weekly | weather | 0.362 | 0.550 |
| weekly | static | 0.308 | 0.496 |
| weekly | spectral | 0.162 | 0.230 |
| weekly | season | 0.092 | 0.200 |
| monthly | weather | 0.381 | 0.597 |
| monthly | static | 0.283 | 0.464 |
| monthly | spectral | 0.160 | 0.241 |
| monthly | season | 0.051 | 0.198 |

Nhận xét:

- Nhóm ERA5/weather và static spatial có tương quan mạnh nhất với salinity.
- Nhóm Sentinel-2/spectral nhìn tổng thể khá yếu, median chỉ khoảng 0.16 và max khoảng 0.23-0.24.
- Tuy nhiên, khi tách theo nhóm khoảng cách tới bờ, một số spectral feature tăng rõ, ví dụ monthly `NDVI_median_week` ở nhóm far-coast có abs Spearman khoảng 0.566. Điều này gợi ý phổ không hoàn toàn vô nghĩa, nhưng quan hệ phụ thuộc tiểu vùng và không ổn định nếu gộp toàn bộ ĐBSCL.
- Vì vậy nên xem Sentinel-2 là feature phụ trợ/tiểu vùng, không phải tín hiệu chính duy nhất để hồi quy salinity toàn vùng.

## Output

Mỗi lần chạy tạo một thư mục trong `outputs/`, gồm:

- `metrics.csv`: metric từng fold/split;
- `predictions.csv`: y_true, y_pred và station holdout;
- `feature_importance.csv`: importance trung bình nếu là XGBoost;
- `feature_columns.txt`: danh sách feature thực sự dùng.

## Ghi chú quan trọng

Notebook gốc có tạo `salinity_lag1` và `salinity_lag2`, nhưng hiện không đưa `LAG` vào `FEATURES`. Script này chủ động loại bỏ tất cả cột mặn khỏi feature để đúng bài toán mapping/spatial estimation.

`source_format` và `completeness_pct` mặc định không dùng làm feature vì dễ trở thành proxy cho protocol đo. Có thể bật để diagnostic:

```bash
--include-source-format
--include-completeness
```

## Hướng chính: Ridge + residual interpolation

`run_regression_kriging.py` triển khai ba mô hình để đối chiếu công bằng:

- `ridge`: trend/drift từ các biến map-ready;
- `idw`: nội suy trực tiếp độ mặn từ các trạm quan trắc;
- `ridge_residual_idw`: Ridge dự đoán trend, sau đó IDW nội suy phần dư.

Đây là phiên bản Regression Kriging thực dụng dùng IDW cho phần dư. Nó không cần
thư viện variogram và phù hợp để kiểm tra giả thuyết trước khi nâng cấp phần nội
suy phần dư sang Ordinary Kriging.

Chạy bài toán lập bản đồ ở cùng thời điểm, trong đó trạm holdout là vị trí chưa đo
nhưng các trạm còn lại vẫn có quan trắc:

```bash
./.venv_lstm/bin/python experiments/xgboost_spatial/run_regression_kriging.py \
  --time-unit weekly \
  --split spatial-cv \
  --residual-source contemporaneous
```

Chạy kịch bản nghiêm ngặt không dùng quan trắc mặn cùng thời điểm:

```bash
./.venv_lstm/bin/python experiments/xgboost_spatial/run_regression_kriging.py \
  --time-unit weekly \
  --split spatiotemporal-cv \
  --residual-source historical
```

`contemporaneous` là thiết kế phù hợp cho nhánh **ước lượng không gian**: số đo ở
các trạm hiện hữu được dùng làm điểm neo để tạo bản đồ tại vị trí không có trạm.
Nó không dùng độ mặn của trạm holdout. `historical` là bài toán ngoại suy cả không
gian lẫn thời gian và thường khó hơn đáng kể.

Kết quả chạy hiện tại (trung bình 5 fold):

| Đơn vị | Split | Model | R2 log | RMSE g/L | MAE g/L |
|---|---|---|---:|---:|---:|
| weekly | spatial-cv | Ridge | 0.272 | 5.641 | 3.595 |
| weekly | spatial-cv | Ridge + residual IDW | 0.257 | 4.765 | 3.035 |
| monthly | spatial-cv | Ridge | 0.397 | 6.000 | 3.533 |
| monthly | spatial-cv | Ridge + residual IDW | 0.301 | 5.827 | 3.342 |
| weekly | spatiotemporal-cv | Ridge + residual IDW | -0.222 | 2.942 | 2.353 |
| monthly | spatiotemporal-cv | Ridge + residual IDW | 0.027 | 2.562 | 2.062 |

Monthly Ridge + residual IDW là cấu hình phù hợp nhất để phát triển tiếp: đây là
cấu hình duy nhất đưa spatiotemporal R2 lên dương, dù mức 0.027 vẫn chỉ nên xem là
baseline ban đầu. Với spatial CV, Ridge đơn có R2 cao hơn nhưng residual IDW giảm
MAE/RMSE ở weekly; vì vậy paper nên báo cáo đủ cả drift-only và mô hình kết hợp.

Để tạo dữ liệu dự đoán toàn vùng, xem `MAPPING_DATA_GUIDE.md` và chạy mẫu
`gee_export_mapping_covariates.js`.

## Bản đồ thử nghiệm tháng 03/2023

Chạy:

```bash
./.venv_lstm/bin/python experiments/xgboost_spatial/run_monthly_grid_mapping.py
```

Pipeline dùng tập feature có thể tái tạo trên grid, sửa dấu ERA5 potential
evaporation, và chỉ giữ pixel có chữ ký nước gần mạng HydroSHEDS. Kết quả spatial
CV trung bình 5 fold:

| Model | R2 log | RMSE g/L | MAE g/L |
|---|---:|---:|---:|
| Ridge reproducible | 0.201 | 5.783 | 3.917 |
| Ridge + residual IDW reproducible | 0.341 | 5.178 | 3.408 |

File dự đoán CSV và GeoJSON nằm trong `outputs/monthly_grid_2023_03/`. Mỗi điểm
có `nearest_anchor_km` và `extrapolation_zone`; không nên diễn giải vùng trên 50
km từ trạm neo như vùng có độ tin cậy tương đương vùng gần trạm.
