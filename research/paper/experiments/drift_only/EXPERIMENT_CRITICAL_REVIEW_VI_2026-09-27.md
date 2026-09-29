# Đánh giá kỹ thực nghiệm trước khi dùng cho camera-ready

Ngày đánh giá: 27/09/2026. Bản cơ sở `run_20260926` được giữ nguyên. Chẩn đoán bổ sung nằm trong `diagnostics/run_20260927`, chạy bằng `diagnose_baseline.py`; không fit lại model, không đổi detector/ngưỡng và không tạo số liệu xác nhận độc lập.

## Kết luận để nhóm quyết định

**Dùng được như một nghiên cứu kiểm soát về sự không tương ứng giữa drift ở đầu vào và chất lượng baseline NIDS. Chưa đủ để chứng minh hiệu quả của toàn bộ framework, concept drift, natural drift hoặc chiến lược retraining.** Giá trị chính là protocol minh bạch và ví dụ có định lượng về giới hạn của tín hiệu drift; không phải phát hiện thuật toán mới.

So với thí nghiệm cũ, bước tiến thực chất là tách reference/evaluation cả benign lẫn attack, có stable controls, giữ model cố định và phân tích nhiều ngưỡng/kích thước. Không nên dùng các cải tiến này để nói rằng mọi vấn đề reviewer nêu đã được giải quyết.

## 1. Số liệu có đúng không?

Verifier đã tải lại model lưu trên đĩa, dự đoán lại 120 cửa sổ, tái tính confusion matrix/metrics, chạy lại 6.240 KS test và đối chiếu BH bằng SciPy. Kết quả khớp; checksum dữ liệu nguồn không đổi. Các pool không trùng vector đặc trưng chính xác. Không thấy lỗi số học làm thay đổi kết luận chính.

Đây là kiểm chứng triển khai và khả năng tái tính, **không phải chứng minh thiết kế thực nghiệm không có bias**. Cùng thuật toán KS vẫn dựa vào giả định thống kê tương tự; verifier cũng không kiểm tra được dữ liệu gốc trước preprocessing.

## 2. S2 chủ yếu đo giới hạn tổng quát hóa và hiệu ứng trộn nhãn

Chẩn đoán hậu nghiệm trên toàn bộ 41.972 dòng evaluation pool, sử dụng model đã khóa:

| Nhãn | Số dòng | Dự đoán ATTACK | Tỷ lệ dự đoán ATTACK |
|---|---:|---:|---:|
| BENIGN | 20.000 | 3 | 0,015% (FPR) |
| DDoS | 10.000 | 9.999 | 99,990% (recall) |
| PortScan | 9.998 | 4 | 0,040% (recall) |
| BruteForce | 1.630 | 60 | 3,681% (recall) |
| WebAttacks | 344 | 0 | 0,000% (recall) |

Model chỉ được học BENIGN/DDoS. Khi thay DDoS bằng các họ gần như luôn bị dự đoán là BENIGN, aggregate recall phải giảm theo tỷ trọng thay thế. Với `r` là phần attack bị thay:

```text
overall_attack_recall = (1-r) × recall_DDoS + r × recall_held_out_families
```

Đã kiểm tra công thức theo đúng số mẫu từng family trong cả 30 cửa sổ S2, khớp với recall đã lưu. Do recall của DDoS gần 1 và recall của họ mới gần 0, đường giảm gần `1-r` có thể giải thích bằng thành phần mixture. Nó không cho thấy model dần mất kiến thức DDoS hay một cơ chế drift gây suy giảm theo thời gian.

**Cách viết phù hợp:** “Increasing the share of held-out attack families lowers aggregate attack recall for a baseline trained on BENIGN/DDoS.” Sau đó đối chiếu cảnh báo để thấy detector bỏ sót một số cửa sổ có suy giảm. Tránh “drift severity causes proportional model degradation” hoặc “we prove concept drift”.

Các số của toàn pool là chẩn đoán hậu nghiệm trên cùng nguồn đánh giá, không phải một tập kiểm thử độc lập mới. Không trộn chúng với bảng mean/SD của 5 seed.

## 3. S1 là đối chứng có ích, nhưng không phải phát hiện mới tổng quát

Đổi prevalence của hai lớp model đã học làm phân phối đặc trưng thay đổi, trong khi decision boundary vẫn hoạt động tốt trên những mẫu đó. Đây là ví dụ thực nghiệm phù hợp để phản bác việc đồng nhất data drift với degradation.

Không gọi cảnh báo S1 là false positive chỉ vì F1 vẫn cao: detector đang nhận diện thay đổi đầu vào có thật. False-alert control trong thiết kế này dựa vào S0. Không mô tả S1 là phép cô lập “pure covariate shift”: việc thay class prior không tự giữ nguyên P(Y|X).

## 4. KS + BH chưa đại diện cho detector triển khai

Đã đọc `services/evidently/src/application.py`: service tạo `DataDriftPreset(drift_share=DRIFT_THRESHOLD)` (hoặc preset mặc định khi cần tương thích), không chỉ định KS hoặc áp BH như runner. Summary còn xử lý missing features/schema mismatch. `requirements.txt` của service pin Evidently 0.4.15.

Do đó không được viết “Evidently missed 4/5 windows” hay “the framework detects these shifts” từ số liệu hiện tại. Cách viết đúng là “the standalone BH-corrected KS monitor”. Chưa chạy service nên không khẳng định test mặc định cụ thể đã được chọn cho từng cột trong môi trường triển khai.

Một phép kiểm tra tích hợp stable/shift qua monitor thật sẽ bổ sung liên hệ với framework, nhưng không thay thế load sweep, natural drift hoặc retraining comparison. Bản camera-ready hiện tại cần nêu rõ ranh giới ngay cả khi chưa chạy được phép kiểm tra đó.

## 5. Độ mạnh của bằng chứng thống kê

- Năm cửa sổ shifted mỗi tổ hợp là ít: 1/5 là một tần suất quan sát, không phải ước lượng đáng tin rằng detector có sensitivity 20% trong production.
- Cùng model, reference và evaluation pool; các cửa sổ có thể dùng lại dòng. Không coi seed lấy mẫu là seed huấn luyện, môi trường mạng mới hay capture độc lập.
- Reference cố định 70/30 và S0 có số lượng lớp cố định. Không mô phỏng dao động prevalence tự nhiên; “0/60 cảnh báo S0” không chứng minh false-alert rate thực tế bằng 0.
- 52 đặc trưng có phụ thuộc và nhiều giá trị trùng. KS tiệm cận/BH là lựa chọn protocol; không suy ra mức kiểm soát lỗi toàn dataset từ q < 0,05.
- Không cần chọn lại ngưỡng để tối đa kết quả đã nhìn thấy. Giữ 0,30 là setting chính và trình bày đầy đủ sweep/correction trade-off.
- Mean ± SD mô tả biến thiên lấy cửa sổ. Nếu công bố confidence interval, cần xác định rõ đại lượng và đơn vị độc lập; không bootstrap các dòng cửa sổ lặp như dữ liệu độc lập ngoài thực tế.

## 6. Leakage, separability và feature importance

Exact dedup và chia lại pool là cải thiện đúng. Tuy nhiên preprocessing upstream chọn đặc trưng trên dữ liệu gộp; timestamp/capture đã mất, nên không thể bảo đảm group independence hoặc train-only feature selection. Nguồn trước subsampling cũng chưa được xác minh byte-level đầy đủ.

Chẩn đoán total training gain của model: Fwd Packet Length Max khoảng 40,27%; Total Length of Fwd Packets 31,47%; Bwd Packet Length Std 14,13%. Ba đặc trưng chiếm khoảng 85,87% total gain. Điều này cho thấy model tập trung vào một số tín hiệu trong nguồn train; **không đủ để kết luận có shortcut cụ thể, leakage hoặc quan hệ nhân quả**. Không được tự nhận Destination Port là nguyên nhân khi chưa có ablation.

Ngược lại, drift share cho mỗi đặc trưng trọng số bằng nhau, kể cả đặc trưng ít được model sử dụng. Đây là một lý do thiết kế khiến drift share không trực tiếp biểu diễn predictive harm, nhưng chưa được ablation để quy trách nhiệm cho từng đặc trưng. Không biến phân tích hậu nghiệm này thành một detector có trọng số đã được kiểm chứng.

## 7. Bản thảo nên giữ, sửa và bỏ gì?

| Nội dung | Quyết định |
|---|---|
| S0/S1/S2, split audit, window/threshold sweep | Giữ làm bằng chứng chính |
| S2 recall giảm | Giải thích bằng held-out-family mixture; không gọi temporal degradation |
| 1/5 alerts | Giữ nguyên, ghi rõ detector KS+BH và 5 windows |
| F1 gần 1 trên DDoS | Ghi giới hạn separability/preprocessing, không lấy làm thành tích SOTA |
| Bảng challenger recovery cũ | Bỏ khỏi evidence chính của bản sửa; giữ lịch sử/artifact để truy vết |
| Architecture/Native Registry | Trình bày trách nhiệm và review boundary; không tự nhận novelty thuật toán |
| Claim production/scalability/secure isolation | Không kết luận khi thiếu đo đạc; giữ bounded replay với cả 4 lỗi 502 và giới hạn |
| Retraining policy | Chỉ nêu hướng thiết kế/future work, chưa claim hiệu quả |

## 8. Việc ưu tiên tiếp theo

1. Sửa Methods/Results/Discussion theo các ranh giới trên; không chỉnh số liệu cơ sở để làm đẹp bài.
2. Hoàn thiện bản short paper 8 trang: rút stack/UI trùng lặp, giữ bảng thực nghiệm, hình sensitivity, provenance và limitations.
3. Lập response matrix đánh dấu đã làm/một phần/chưa làm cho từng ý reviewer; sửa metadata citations và kiểm tra claim-to-source.
4. Nhóm chốt nguồn CSV có version/checksum và một người khác tái chạy. Audit local chưa thay thế artifact public đầy đủ.
5. Chỉ bổ sung tích hợp detector nếu môi trường sẵn; không mở CT, dataset hoặc training-policy search ngay trước deadline.

**Đánh giá cuối:** bộ số liệu mới có ích để làm paper trung thực và có phương pháp hơn. Nó không tự nâng paper thành nghiên cứu có novelty mạnh hay giải quyết đầy đủ hai review. Việc quan trọng lúc này là giới hạn đúng đóng góp, giải thích S2 và đóng gói bản thảo có thể kiểm chứng.
