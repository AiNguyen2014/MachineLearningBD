# Báo cáo mô hình đa nguồn MS-LSTM

## Ba mô hình so sánh

1. **Persistence:** dự báo bằng giá trị mặn gần nhất trong cửa sổ đầu vào.
2. **LSTM-S:** LSTM residual chỉ dùng lịch sử mặn, trạng thái quan trắc và mùa vụ.
3. **MS-LSTM:** mô hình đề xuất dùng mặn + ERA5-Land hằng ngày + Sentinel-2 composite tháng trước.

Persistence không cần huấn luyện. LSTM-S và MS-LSTM có checkpoint riêng; MS-LSTM là mô hình chính phù hợp với hướng đa nguồn của đề tài.

## Kiến trúc MS-LSTM

- Cửa sổ đầu vào 30 ngày, dự báo trước 1 ngày.
- Nhánh động: 7 biến mặn/trạng thái/mùa vụ và 13 biến ERA5-Land được mã hóa bằng LSTM 1 tầng, 128 hidden units.
- Nhánh ngữ cảnh: tọa độ và 10 biến Sentinel-2 chọn lọc được mã hóa bằng MLP 32 units.
- Station embedding 8 chiều; fusion head 64 units; dropout 0.15.
- Mô hình dự báo residual so với giá trị mặn gần nhất, dùng Huber loss và AdamW.
- Train 2020-2021, validation 2022, test 2023. Chọn kiến trúc và seed theo validation RMSE.

## Kết quả test 2023

| Mô hình | RMSE | MAE | R² |
|---|---:|---:|---:|
| Persistence | 1.328 | 0.730 | 0.957 |
| LSTM-S | 1.265 | 0.704 | 0.961 |
| MS-LSTM ensemble | 1.278 | 0.746 | 0.961 |

MS-LSTM ba seed có test RMSE trung bình **1.300 ± 0.016**. Ensemble dùng trung bình dự đoán của ba seed.

## Ablation nguồn dữ liệu

Trên validation 2022, LSTM-S đạt RMSE 1.220; thêm ERA5 đạt 1.191; thêm cả ERA5 và Sentinel-2 đạt tốt nhất 1.133 ở seed được chọn. Điều này cho thấy dữ liệu GEE tạo cải thiện trên tập dùng để lựa chọn mô hình. Trên test 2023, chênh lệch giữa LSTM-S và MS-LSTM nhỏ hơn và có thể đảo chiều, do đó cần external test 2025 để đánh giá khả năng tổng quát hóa.

## Cách báo cáo trong paper

MS-LSTM nên được trình bày là mô hình đa nguồn đề xuất; LSTM-S là ablation và Persistence là baseline. Không nên chỉ dựa vào R²: cần báo cáo cả RMSE, MAE, kết quả theo trạm, nhiều seed và external test. Toàn bộ trial nằm trong `tuning_results.csv`.
