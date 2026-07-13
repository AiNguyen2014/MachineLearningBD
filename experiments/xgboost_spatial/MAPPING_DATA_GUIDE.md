# Dữ liệu cần bổ sung để dự đoán toàn vùng

Dataset hiện tại đủ để huấn luyện và kiểm định leave-station-out, nhưng chỉ chứa
feature tại vị trí trạm. Để tạo bản đồ, cần một bảng covariate tại toàn bộ các
điểm cần dự đoán; bảng này **không có cột độ mặn**.

## 1. Bản chạy thử không cần asset cá nhân

Script hiện tự tạo dữ liệu đầu vào từ collection công khai:

- ROI 13 tỉnh/thành từ `FAO/GAUL_SIMPLIFIED_500m/2015/level1`;
- lưới điểm 2 km trong hệ chiếu UTM 48N (`EPSG:32648`);
- sông từ `WWF/HydroSHEDS/v1/FreeFlowingRivers`.

HydroSHEDS có độ phân giải nguồn khoảng 500 m và không thể hiện đầy đủ mọi kênh
nội đồng nhỏ. Vì vậy đây là dữ liệu baseline có thể tái tạo, chưa phải lớp sông
chi tiết cuối cùng.

Script không xuất `Distance_to_Coast_first`, vì chưa có public collection nào
được xác nhận giống cách biến này được tạo trong CSV train. Khi nhận CSV grid,
mô hình sẽ được train lại bằng đúng tập feature tái tạo được, thay vì impute biến
khoảng cách bờ trên toàn bản đồ.

## 2. Xuất feature cho từng thời điểm

Mở `gee_export_mapping_covariates.js` trong GEE Code Editor, chỉnh `start`, `end`
và `exportName`, rồi Run và chạy task trong tab Tasks. Không cần upload asset.

Nên ưu tiên **monthly** cho nhánh không gian vì kiểm định hiện tại ổn định hơn
weekly. Mỗi file là một tháng, hoặc sửa script để ghép nhiều tháng sau khi một
tháng mẫu đã được kiểm tra đúng schema.

## 3. Các biến còn thiếu cần thống nhất

Script đã xuất Sentinel-2, DEM và phần lớn ERA5. Dataset train còn các biến như
wind, rainy-day count và một số tên tổng hợp riêng. Trước khi tạo bản đồ cuối,
cần một trong hai lựa chọn:

- bổ sung cách tính chính xác các biến đó theo pipeline đã tạo CSV train; hoặc
- huấn luyện lại Ridge với tập con feature có thể tái tạo giống hệt trên grid.

Lựa chọn thứ hai an toàn hơn khi không còn code tiền xử lý gốc. Pipeline Ridge
dùng median imputation nên chạy được khi thiếu cột theo hàng, nhưng file predict
vẫn phải có đúng danh sách cột trong `feature_columns.txt`.

## 4. Quan trắc dùng làm điểm neo phần dư

Với mỗi tháng cần lập bản đồ, cần bảng mặn ở các trạm hiện hữu gồm tối thiểu:

```text
station_id,date,lon_first,lat_first,salinity_max_mean
```

Độ mặn này chỉ dùng để tính phần dư tại trạm neo. Vị trí trên grid và các trạm
holdout không có độ mặn đầu vào. Nếu không có quan trắc cùng tháng, mô hình chỉ
còn Ridge/historical residual và kết quả hiện tại cho thấy chưa đủ tin cậy.

## 5. Kiểm tra trước khi ghép

- CRS/toạ độ và đơn vị khoảng cách thống nhất.
- Cửa sổ thời gian của Sentinel-2, ERA5 và nhãn mặn giống nhau.
- Không đưa `station_id`, salinity lag, `source_format` hay completeness vào
  feature dự đoán.
- Báo cáo riêng kết quả `spatial-cv` và `spatiotemporal-cv`; không dùng temporal
  split để chứng minh khả năng dự đoán vị trí mới.
