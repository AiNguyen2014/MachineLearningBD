# Báo cáo mô hình đa nguồn MS-LSTM

## Các mô hình so sánh

1. **Persistence:** dự báo bằng giá trị mặn gần nhất trong cửa sổ đầu vào.
2. **LSTM-S:** LSTM residual chỉ dùng lịch sử mặn, trạng thái quan trắc và mùa vụ.
3. **MS-only:** mô hình đa nguồn không dùng lịch sử mặn; đầu vào gồm ERA5-Land, Sentinel-2, tọa độ, mùa vụ và định danh trạm.
4. **MS-LSTM:** mô hình đề xuất dùng mặn + ERA5-Land hằng ngày + Sentinel-2 composite tháng trước.

Persistence không cần huấn luyện. LSTM-S, MS-only và MS-LSTM có checkpoint riêng; MS-LSTM là mô hình chính phù hợp với hướng đa nguồn của đề tài.

## Kiến trúc MS-LSTM

- Cửa sổ đầu vào 30 ngày, dự báo trước 7 ngày.
- Nhánh động: 7 biến mặn/trạng thái/mùa vụ và 13 biến ERA5-Land được mã hóa bằng LSTM 1 tầng, 128 hidden units.
- Nhánh ngữ cảnh: tọa độ và 10 biến Sentinel-2 chọn lọc được mã hóa bằng MLP 32 units.
- Station embedding 8 chiều; fusion head 64 units; dropout 0.15.
- Mô hình dự báo residual so với giá trị mặn gần nhất, dùng Huber loss và AdamW.
- Train 2020-2021, validation 2022, test 2023. Chọn kiến trúc và seed theo validation RMSE.

## Kết quả test 2023 cho horizon 7 ngày

| Mô hình | RMSE | MAE | R² |
|---|---:|---:|---:|
| Persistence | 3.174 | 2.144 | 0.759 |
| LSTM-S | 2.620 | 1.813 | 0.836 |
| MS-only | 3.595 | 2.814 | 0.691 |
| MS-LSTM ensemble | 2.769 | 1.978 | 0.817 |

MS-LSTM ba seed có test RMSE trung bình **2.855 ± 0.056**. Ensemble dùng trung bình dự đoán của ba seed.

MS-only không dùng giá trị mặn lịch sử, chỉ dùng ERA5-Land, Sentinel-2, tọa độ, mùa vụ và station embedding; trên cùng tập test so sánh, mô hình đạt RMSE **3.595**, MAE **2.814**, R² **0.691**.



## Ablation nguồn dữ liệu

Trên validation 2022, các cấu hình horizon 7 ngày được so sánh để kiểm tra mức độ đóng góp của từng nguồn dữ liệu. MS-only là thí nghiệm bổ sung để kiểm tra mức độ dữ liệu ngoại sinh có thể giải thích độ mặn khi không có mặn lịch sử. Điều này giúp tách hai câu hỏi: giá trị mặn quá khứ mạnh đến đâu, và dữ liệu khí tượng - viễn thám tự thân đóng góp bao nhiêu. Trên test 2023, cần diễn giải đồng thời Persistence, LSTM-S, MS-only và MS-LSTM để tránh chỉ dựa vào R².

## Cách báo cáo trong paper

MS-LSTM nên được trình bày là mô hình đa nguồn đề xuất; LSTM-S và MS-only là ablation, Persistence là baseline. Không nên chỉ dựa vào R²: cần báo cáo cả RMSE, MAE, kết quả theo trạm, nhiều seed và external test. Toàn bộ trial nằm trong `tuning_results.csv`.
