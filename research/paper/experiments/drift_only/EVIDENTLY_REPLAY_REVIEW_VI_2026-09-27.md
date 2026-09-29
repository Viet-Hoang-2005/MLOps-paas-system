# Đối chiếu Evidently với thực nghiệm drift đã khóa — nhận xét kiểu reviewer

Ngày chạy: 27/09/2026. Đây là **thực nghiệm mới, tách khỏi** `results/run_20260926`; không huấn luyện lại, không đổi split, model, reference, cửa sổ hoặc nhãn. Không diễn giải các số dưới đây là kết quả chạy end-to-end trên deployment.

## Câu hỏi và phương pháp

Paper báo cáo KS hai mẫu + Benjamini–Hochberg (BH) trên 52 feature, ngưỡng drift-share chính 0,30. Service trong repo chạy `DataDriftPreset` của Evidently và kết luận alert khi tỷ lệ feature bị đánh dấu đạt `DRIFT_THRESHOLD` (mặc định 0,60). Hai phép đo **không tương đương**; cần biết liệu kết luận offline có còn đúng với detector mà hệ thống cấu hình hay không.

`compare_evidently.py` lấy chính xác reference 5.000 dòng và row membership của 120 cửa sổ đã lưu. Input cho Evidently chỉ có 52 numeric feature; không đưa `Label` vào phép phát hiện. Với mỗi cửa sổ, script gọi `DataDriftPreset(drift_share=0.6)`, đếm các feature có `drift_detected=true` như `services/evidently/src/application.py`, rồi xét ngưỡng 0,60. Ngưỡng 0,30 được tính thêm như **phân tích đối chiếu**, không phải cấu hình production. Macro-F1/recall và KS/BH được đọc nguyên từ baseline, không tính lại ở đây.

Môi trường riêng dùng Python 3.11.14, Evidently 0.4.15, pandas 2.0.3, NumPy 1.26.4 và Pydantic 1.10.13. Evidently là **đúng version khai báo trong service**, nhưng các dependency khác có thể không trùng image đã triển khai; khóa môi trường đầy đủ nằm ở `results/evidently_20260927/environment.lock.txt`. Local Docker daemon không hoạt động, nên chỉ gọi trực tiếp thư viện Evidently, không chạy container, PostgreSQL, Redpanda, S3 hoặc webhook. Trong run này Evidently dùng **Wasserstein distance (normed)** cho 49 feature và **Jensen–Shannon distance** cho 3 feature, với `stattest_threshold=0.1` — không phải KS/BH.

## Kết quả

Tất cả 120 cửa sổ và 6.240 kết quả theo feature đã được ghi; bộ kiểm tra độc lập về checksum đầu vào, membership, feature count và phép tổng hợp báo `passed` trong `verification.json`. Bảng dưới chỉ lấy các cửa sổ **n=1.000**. Mỗi S0 có 30 cửa sổ; mỗi tình huống khác có năm. Ký hiệu là số alert/số cửa sổ.

| Tình huống | Attack recall TB | KS/BH 0,30 | Evidently 0,30 | KS/BH 0,60 | Evidently 0,60 |
|---|---:|---:|---:|---:|---:|
| S0, thành phần giữ nguyên | 0,9999 | 0/30 | 0/30 | 0/30 | 0/30 |
| S1, 15% attack | 1,0000 | 5/5 | 3/5 | 5/5 | 0/5 |
| S1, 50% attack | 1,0000 | 5/5 | 5/5 | 5/5 | 0/5 |
| S1, 85% attack | 0,9998 | 5/5 | 5/5 | 5/5 | 5/5 |
| S2, thay 25% attack | 0,7533 | 1/5 | 0/5 | 0/5 | 0/5 |
| S2, thay 50% attack | 0,5080 | 5/5 | 4/5 | 5/5 | 0/5 |
| S2, thay 100% attack | 0,0100 | 5/5 | 5/5 | 5/5 | 1/5 |

Gộp hai cỡ cửa sổ: **60/60 S0** không alert dưới cả hai detector ở các ngưỡng 0,30 và 0,60. Trên **60 cửa sổ được tạo có shift**, Evidently 0,60 báo 13/60, KS/BH 0,60 báo 45/60. Ở cùng ngưỡng 0,30, các số lần lượt là 48/60 và 52/60; hai detector bất đồng ở tám cửa sổ. Đây là tần suất có điều kiện trong mẫu đã tạo, **không phải sensitivity/specificity production**.

Điểm đáng chú ý nhất: ở `S2_r50`, n=1.000, recall giảm còn khoảng 0,508 nhưng Evidently ở cấu hình 0,60 không báo cửa sổ nào; ở `S2_r100`, recall gần 0,010 nhưng chỉ báo 1/5. Trong khi đó S1 85% được báo 5/5 dù recall gần như không đổi. Như vậy drift-share của preset không xếp hạng tác hại dự đoán trong các tình huống này. Ngay cả khi xét thử ngưỡng 0,30, S2 25% n=1.000 vẫn 0/5 alert. Việc giảm recall của S2 chủ yếu do trộn các họ attack mà model BENIGN/DDoS chưa học; không phải bằng chứng model mất kiến thức theo thời gian hay concept drift.

## Đánh giá như reviewer

**Giá trị:** Đây là bước nối đúng giữa phương pháp offline và một thành phần thật của framework: cùng dữ liệu, cùng reference/window, đúng Evidently version, và có kết quả per-feature để audit. Nó củng cố insight chính của bài — cảnh báo phân bố và chất lượng dự đoán là hai loại evidence cần tách riêng — đồng thời phơi bày rủi ro nếu paper dùng số KS/BH để mô tả service.

**Giới hạn lớn:** Đây vẫn là replay thư viện offline, chưa xác minh model-server → broker → consumer → PostgreSQL → monitor → callback. Detector của service có thể nhận reference asset, kiểu dữ liệu, MLflow signature, cửa sổ lấy theo timestamp hoặc cấu hình khác khi vận hành. Reference/cửa sổ trong bài được lấy từ dataset đã tiền xử lý, xáo trộn, không có mốc thời gian/capture; model cố định và cửa sổ chia sẻ evaluation pool. Năm cửa sổ shifted mỗi setting quá ít cho ước lượng độ nhạy ngoài mẫu. Không có so sánh retraining/lifecycle, natural drift, nhiều model/tenant hay tải đồng thời. Kết quả này không giải quyết các yêu cầu đó của Reviewer 1/2.

**Khuyến nghị biên tập:** Có thể thêm **một đoạn ngắn** vào Results/Discussion, nêu rõ `DataDriftPreset` 0.4.15 ở ngưỡng cấu hình 0,60 bỏ qua S2 50% (0/5) và phần lớn S2 100% (1/5) tại n=1.000, nhưng đây chỉ là replay offline. Nếu đưa bảng chi tiết vào paper 8 trang, nên thay nội dung kém quan trọng chứ không ép cỡ chữ/lề. Không đổi ngưỡng production theo dữ liệu đã nhìn thấy. Mọi quyết định retrain/promotion vẫn phải dựa thêm vào nhãn, kiểm thử challenger và review; không được tuyên bố policy ấy đã được thực nghiệm.

**Phán quyết trong vai reviewer:** Tôi coi đây là **bổ sung hữu ích nhưng chưa đủ** để xác nhận hiệu quả của toàn framework. Bài mạnh hơn khi biến detector mismatch thành kết quả trung thực và làm rõ ranh giới evidence. Tôi vẫn yêu cầu nguồn dữ liệu có version tái lập được, một lần tái chạy độc lập, và diễn giải rõ những yêu cầu chưa hoàn thành trước camera-ready. Cụm “citation-integrity trigger” trong review vẫn cần được kiểm tra riêng.

## Artifact và chạy lại

Từ root repo, với môi trường Python 3.11 và các phiên bản trong `environment.lock.txt`:

```powershell
python research/paper/experiments/drift_only/compare_evidently.py --output research/paper/experiments/drift_only/results/evidently_reproduction
python research/paper/experiments/drift_only/verify_evidently.py research/paper/experiments/drift_only/results/evidently_reproduction
```

Script từ chối ghi đè thư mục kết quả đã có. Dữ liệu nguồn tại `data/reference_data.csv` đã được đối chiếu SHA-256 với baseline trước khi chạy. Các file chính là `window_comparison.csv`, `feature_comparison.csv`, `scenario_comparison.csv`, `manifest.json` và `verification.json` trong `results/evidently_20260927/`.
