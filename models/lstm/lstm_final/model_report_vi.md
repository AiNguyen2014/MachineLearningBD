# Báo cáo mô hình LSTM dự báo độ mặn theo ngày

## Thiết kế thí nghiệm

- Dữ liệu: 22 trạm, giai đoạn 2020-2023; target là độ mặn cực đại quan trắc.
- Chia theo thời gian: train đến 31/12/2021, validation năm 2022, test năm 2023.
- Bài toán chính: dự báo trước 7 ngày từ cửa sổ 30 ngày; scaler và median imputer chỉ fit trên train.
- Chọn mô hình hoàn toàn theo RMSE validation. Test 2023 không được dùng để chọn siêu tham số.
- Cấu hình cuối: nhóm biến `salinity`, LSTM 1 tầng, 128 hidden units, dropout 0.15, Huber loss, station embedding 8 chiều.

## Kết quả chính

Ba seed độc lập cho test RMSE trung bình **2.683 ± 0.120**. Ensemble trung bình ba seed đạt RMSE **2.559**, MAE **1.852**, R² **0.842** trên 2,774 mẫu test năm 2023.

Theo trạm, RMSE tốt nhất là **TUYEN_NHON (0.381)** và cao nhất là **XEO_RO (5.332)**. Chi tiết nằm trong `test_metrics_by_station.csv` và `test_metrics_by_month.csv`.

## Ablation và tuning

Thử nghiệm ablation horizon 7 ngày cho thấy nhóm biến lịch sử mặn, trạng thái quan trắc, tọa độ và mùa vụ vẫn là một baseline LSTM quan trọng. Toàn bộ cấu hình và metric được lưu trong `tuning_results_all.csv`.

## Baseline bắt buộc phải báo cáo

Trên 2,596 mẫu có giá trị mặn đầu vào ở cuối cửa sổ, persistence baseline t-7 đạt RMSE **3.178**, trong khi LSTM ensemble đạt **2.556** trên đúng tập mẫu đó. Với horizon 7 ngày, baseline persistence yếu hơn và mô hình LSTM có thêm không gian để học động lực biến đổi theo tuần.

## Diễn giải và giới hạn

Kết quả phù hợp để trình bày như một baseline LSTM horizon 7 ngày và một kết quả ablation trung thực. Các hướng tiếp theo nên ưu tiên residual forecasting so với persistence, đánh giá theo trạm/mùa, và kiểm định ngoài mẫu trên 2025. ERA5/Sentinel-2 có thể hữu ích hơn ở horizon dài hoặc trong bài toán ước lượng không gian.

## External test 2025

Raw 2025 hiện có 8/22 trạm: BinhDai, AnThuan, BenTrai, LocThuan, TraVinh, CauNoi, TanAn và BenLuc. Có thể dùng làm external temporal test trên tập trạm giao nhau. Phải giữ nguyên preprocessing, scaler, feature set và checkpoint; không tune theo 2025. Vì cấu hình cuối chỉ dùng nhóm biến mặn, không bắt buộc lấy ERA5/Sentinel-2 2025 cho phép thử này.

## Tái lập

Chạy `python tune_lstm.py` để tái lập search ban đầu và `python evaluate_lstm.py` để tạo lại các bảng báo cáo. Mỗi trial lưu config, seed, lịch sử epoch, checkpoint, prediction và metric trong thư mục riêng.
