# Báo cáo mô hình LSTM dự báo độ mặn theo ngày

## Thiết kế thí nghiệm

- Dữ liệu: 22 trạm, giai đoạn 2020-2023; target là độ mặn cực đại quan trắc.
- Chia theo thời gian: train đến 31/12/2021, validation năm 2022, test năm 2023.
- Bài toán chính: dự báo trước 1 ngày từ cửa sổ 30 ngày; scaler và median imputer chỉ fit trên train.
- Chọn mô hình hoàn toàn theo RMSE validation. Test 2023 không được dùng để chọn siêu tham số.
- Cấu hình cuối: nhóm biến `salinity`, LSTM 1 tầng, 128 hidden units, dropout 0.15, Huber loss, station embedding 8 chiều.

## Kết quả chính

Ba seed độc lập cho test RMSE trung bình **1.393 ± 0.025**. Ensemble trung bình ba seed đạt RMSE **1.370**, MAE **0.856**, R² **0.955** trên 2,774 mẫu test năm 2023.

Theo trạm, RMSE tốt nhất là **XUAN_KHANH (0.207)** và cao nhất là **BEN_TRAI (3.978)**. Chi tiết nằm trong `test_metrics_by_station.csv` và `test_metrics_by_month.csv`.

## Ablation và tuning

Thử nghiệm ablation cho thấy nhóm biến chỉ gồm lịch sử mặn, trạng thái quan trắc, tọa độ và mùa vụ cho kết quả validation tốt nhất. Việc thêm ERA5 hoặc Sentinel-2 theo tháng không cải thiện RMSE trong thiết lập dự báo ngày kế tiếp. Kết quả này hợp lý với tính tự tương quan mạnh của độ mặn ngày và độ phân giải thời gian thấp hơn của composite Sentinel-2. Toàn bộ cấu hình và metric được lưu trong `tuning_results_all.csv`.

## Baseline bắt buộc phải báo cáo

Trên 2,680 mẫu có giá trị mặn đầu vào ở ngày liền trước, persistence baseline đạt RMSE **1.204**, trong khi LSTM ensemble đạt **1.240** trên đúng tập mẫu đó. Như vậy LSTM hiện chưa vượt baseline persistence cho dự báo 1 ngày. R² cao của LSTM vẫn đúng, nhưng chưa đủ để khẳng định lợi ích dự báo so với quy tắc đơn giản.

## Diễn giải và giới hạn

Kết quả phù hợp để trình bày như một baseline LSTM mạnh và một kết quả ablation trung thực, nhưng chưa nên tuyên bố mô hình cuối có ưu thế vận hành ở horizon 1 ngày. Các hướng tiếp theo nên ưu tiên dự báo 3/7 ngày, residual forecasting so với persistence, và đánh giá trên 2025. ERA5/Sentinel-2 có thể hữu ích hơn ở horizon dài hoặc trong bài toán ước lượng không gian, dù chưa giúp thiết lập LSTM hiện tại.

## External test 2025

Raw 2025 hiện có 8/22 trạm: BinhDai, AnThuan, BenTrai, LocThuan, TraVinh, CauNoi, TanAn và BenLuc. Có thể dùng làm external temporal test trên tập trạm giao nhau. Phải giữ nguyên preprocessing, scaler, feature set và checkpoint; không tune theo 2025. Vì cấu hình cuối chỉ dùng nhóm biến mặn, không bắt buộc lấy ERA5/Sentinel-2 2025 cho phép thử này.

## Tái lập

Chạy `python tune_lstm.py` để tái lập search ban đầu và `python evaluate_lstm.py` để tạo lại các bảng báo cáo. Mỗi trial lưu config, seed, lịch sử epoch, checkpoint, prediction và metric trong thư mục riêng.
