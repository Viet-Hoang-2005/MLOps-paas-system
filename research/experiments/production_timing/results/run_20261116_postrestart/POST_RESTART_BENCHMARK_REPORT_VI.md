# Benchmark sau khi bật lại EC2

Ngày thực hiện theo giờ Việt Nam là 16/11/2026. Timestamp UTC trong dữ liệu raw thuộc tối 15/11.

## Kết quả đưa vào slide

- Median của ba p95 inference là **162 ms**.
- Median thời gian nhận report là **39.2 giây**, với **3/3 cửa sổ** hoàn tất.

Ba lượt có tổng cộng **3.000/3.000 response hợp lệ**, đủ 3.000 record và không có dự đoán lệch baseline đóng băng. Mỗi lượt phát đúng 1.000 request với tải mục tiêu 5 request/giây, tối đa 10 request đồng thời. Mỗi lượt được audit và cleanup riêng.

| Lượt | Response | Record lưu | p95 inference, ms | Report availability, s |
|---|---|---|---|---|
| 1 | 1000/1000 | 1000 | 165.65 | 47.97 |
| 2 | 1000/1000 | 1000 | 161.78 | 33.55 |
| 3 | 1000/1000 | 1000 | 159.93 | 39.20 |

p95 tính trên response thành công, từ trước POST tới khi máy khách đọc xong body qua HTTPS public. Thời gian nhận report tính từ trước khi phát request cuối tới khi run hoàn tất và tải được cả JSON lẫn HTML. Phép đo gồm persistence, trigger, scheduling, chạy detector, callback, polling hai giây và tải HTML khoảng 5,7 MB.

## Đối chiếu hai đợt

| Đợt | Response hợp lệ | Lỗi máy khách | Median p95, ms | Median report, s | Report hoàn tất |
|---|---|---|---|---|---|
| Đợt trước | 2999/3000 | 1 ReadError | 355.13 | 44.86 | 2/3 |
| Sau bật lại EC2 | 3000/3000 | 0 | 161.78 | 39.20 | 3/3 |

Đợt trước vẫn giữ nguyên trong run_20261115, gồm request ReadError chỉ để lại 999 record và không kích hoạt report. Hai đợt được trình bày riêng. Các con số sau reboot là phép kiểm chứng bổ sung theo yêu cầu bật lại cụm, với cùng model, reference và cửa sổ S0. Môi trường và tải nền được ghi riêng theo từng đợt.

## Khôi phục và cấu hình

AWS CLI đã bật master t3.medium và hai worker t3.large đang stopped. Sau quá trình bootstrap, ba node Ready và model health có xác thực trả HTTP 200. Các lỗi ImagePull và trạng thái pod Unknown trong giai đoạn khởi động đã tự phục hồi trước warm-up. Đợt này dùng lại deployment và cấu hình đã có.

Gói serving kế thừa native MLflow XGBoost CPU 3.2.0 đã kiểm chứng ở đợt trước, cùng 200 cây và 12.000 nhãn dự đoán đóng băng. Các sửa chữa trước đợt đầu gồm tăng resource riêng pod notify, restart standby PostgreSQL để phục hồi replication và thêm policy gateway tới JWKS TCP/8000. Báo cáo đợt trước giữ chi tiết và biên nhận những thao tác đó.

## Kiểm chứng và trạng thái cuối

Bộ kiểm chứng độc lập đã tính lại ba p95 từ requests.jsonl, ba duration từ monotonic timestamps, đối chiếu 3.000 prediction theo baseline, audit ID và 52 feature, kiểm tra HTML và xác nhận mọi biên nhận cleanup có zero record còn lại. independent-verification.json và evidence-checksums.json lưu kết quả kiểm chứng.

Model vẫn healthy, không còn prediction record hoặc monitor đang active của benchmark. Ba EC2 tiếp tục chạy sau phép đo. Các image, resource và node được lưu trong environment-before.json cùng environment-after.json.

Phạm vi bằng chứng gồm một classifier, một cửa sổ S0 lặp lại và một mức tải. Độ trễ bao gồm đường mạng từ máy khách. Việc giải thích kết quả cần giữ phạm vi này.

## Slide bàn giao

Bản CSONET_2026_Presentation_Post_Restart.pptx và PDF tương ứng ở thư mục output bổ sung hai số đo lên slide 18. Speaker notes song ngữ ghi đầy đủ nguồn, định nghĩa phép đo và lỗi ReadError của đợt trước. Bản gốc và bản slide của đợt trước được giữ lại.

Các cache chart kế thừa từ nguồn được đồng bộ theo workbook nhúng với sai khác dưới 1e-12, giữ nguyên giá trị hiển thị đến sáu chữ số thập phân. Mọi slide ngoài slide 18 được đối chiếu render với bản gốc.
