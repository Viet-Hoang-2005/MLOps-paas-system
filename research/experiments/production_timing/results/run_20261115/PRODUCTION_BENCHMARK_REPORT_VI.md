# Kết quả benchmark production CSoNet

## Hai số liệu đưa vào slide 18

- **Median client inference p95 đạt 355 ms**, lấy median của p95 từng lượt. p95 tính trên response thành công.
- **Median window-to-report availability đạt 44.9 giây**, tổng hợp trên **2/3 cửa sổ** có report hoàn tất.

Ba lượt cùng dùng S0_n1000_s42, cùng baseline XGBoost và reference 5.000 hàng. Mỗi lượt phát 1.000 request, tải mục tiêu 5 request/giây, tối đa 10 request đồng thời. Máy khách Windows gọi HTTPS public qua ingress/gateway tới worker. Chất lượng dự đoán đối chiếu theo baseline đóng băng.

| Lượt | Response hợp lệ | Record đã lưu | p95 thành công, ms | Thời gian report, s |
|---|---|---|---|---|
| 1 | 999/1000 | 999 | 364.40 | Không kích hoạt |
| 2 | 1000/1000 | 1000 | 184.15 | 50.47 |
| 3 | 1000/1000 | 1000 | 355.13 | 39.24 |

## Lỗi quan sát được và cách diễn giải

Lượt đầu có một **ReadError** tại máy khách, kéo dài khoảng 19,25 giây. Request đó không có record tương ứng trong PostgreSQL. Window có 999 record, dưới ngưỡng kích hoạt 1.000, nên không có thời gian report. Lượt này được giữ trong kết quả theo lựa chọn của người dùng. Các lượt sau dùng cùng tải và input, không tự retry inference. Mẫu số của số đo report được ghi rõ trên slide.

Độ trễ p95 đo từ trước khi gửi POST tới khi đọc xong response body. Thời gian report bắt đầu trước request cuối cùng và kết thúc khi trạng thái hoàn tất, JSON report và HTML report đều truy cập được. Chu kỳ polling hai giây cùng thời gian truy xuất report qua mạng nằm trong phép đo. HTML Evidently có dung lượng khoảng 5,7 MB.

Đây là timing của replay có kiểm soát trên cụm triển khai lại tháng 11/2026. Các số drift/recall của replay tháng 9 trong slide giữ nguồn riêng. Các phép đo hiện tại có phạm vi một model, một mức tải và ba lượt đã lên lịch.

## Chuẩn bị và phục hồi trước phép đo

1. Gói model cũ dùng code-model loader bị validator hiện tại từ chối. Gói mới dùng native MLflow XGBoost CPU 3.2.0. Đã kiểm chứng 200 cây, danh sách feature và objective giữ nguyên, cùng 12.000 dự đoán đóng băng không có sai khác nhãn.
2. Build native đầu tiên bị OOM tại 512 MiB khi cài dependency. Wheel CPU và các phiên bản pandas/NumPy của serving base giải quyết bước này.
3. Tăng riêng pod notify của build từ 64 MiB/100m CPU lên 512 MiB/500m CPU để hoàn tất callback. Thay đổi được lưu trong notify-pod-resize.json.
4. Khởi động lại standby postgresql-2 và rút thời gian dừng pod từ 1.800 xuống 30 giây để phục hồi WAL replication. Primary và PVC được giữ lại.
5. Bổ sung NetworkPolicy np-mlops-paas-control-plane-jwks, chỉ cho pod gateway kết nối Control Plane TCP/8000 để lấy public JWKS. Fix có trong source local và đã áp dụng lên cụm.

Các lỗi chuẩn bị được lưu riêng. preflight_404 chứa warm-up 404. observer_preflight chứa một lượt report đã hoàn tất nhưng bị phiên bản đầu của bộ đo từ chối nhầm vì dùng HTML fragment. Hai nhóm này có bằng chứng đầy đủ và tách khỏi ba lượt chính thức ở bảng trên.

## Bằng chứng và kiểm chứng

repeat_1 tới repeat_3 lưu request timings, record database, audit, trạng thái report và biên nhận cleanup. summary.json và repeat_summary.csv giữ số liệu đầy đủ. Bản kiểm chứng độc lập tính lại các percentile và duration từ dữ liệu raw. Các query ký truy cập trong URL artifact đã được lọc khỏi ba bản report-data.json, giữ nguyên toàn bộ metrics.

Phần persistence kiểm tra ID, request ID, feature values và prediction. Chỉ record do benchmark tạo được xóa giữa các lượt. Mọi monitor benchmark đã hoàn tất được tắt. Model test vẫn sẵn sàng để nhóm kiểm tra.

Kiểm thử local gồm 10 test audit/client và 51 validation K8s. Runtime worker đo được Python 3.10.22, XGBoost module 3.2.0, MLflow 3.11.1, NumPy 1.26.4 và pandas 2.2.1. Runtime detector đo được Evidently 0.4.15, NumPy 1.26.4, pandas 2.0.3, SciPy 1.15.3 và MLflow 2.13.2. Image identity và resource inventory nằm trong các file environment.

## Bản slide cập nhật

Slide 18 bổ sung hai số đo, mẫu số report hoàn tất và 1 ReadError trên 3.000 request. Các slide còn lại giữ nguyên ảnh render. Bản gốc có cache của năm chart lệch workbook ở mức dưới 1e-12. Bản cập nhật đồng bộ cache theo workbook đang nhúng, giữ nguyên công thức, dữ liệu workbook và các giá trị hiển thị đến sáu chữ số thập phân. Bản PowerPoint gốc trong research/slide/ được giữ làm nguồn.
