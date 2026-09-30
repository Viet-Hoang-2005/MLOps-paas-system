# Kế hoạch một tuần: kiểm chứng data drift và suy giảm chất lượng NIDS

**Kế hoạch gốc:** 24/09/2026. **Cập nhật:** 27/09/2026. **Hạn camera-ready:** 30/09/2026.
**Phạm vi:** một case study CIC-IDS2017, một mô hình NIDS cố định. Tiếp tục E-D1/S0–S2 và E-D2 của kế hoạch gốc từ các kết quả đã có. Chưa phát triển continuous training, chưa thêm dataset/case study.

Đây là **kế hoạch chính để giao việc**. Bản này tập trung vào nội dung thực nghiệm, số liệu và cách diễn giải. Các phần dựng cụm, kiểm tra EC2 và benchmark tải của bản trước được đưa ra ngoài phạm vi công việc này. Replay qua service, nếu thực hiện, chỉ kiểm chứng luồng inference → lưu dữ liệu → drift report trên cùng cửa sổ đã đánh giá offline.

## 1. Cần chứng minh điều gì?

Câu hỏi chính: **Khi thành phần traffic thay đổi, detector có cảnh báo không; mô hình cố định có suy giảm chất lượng không; hai kết quả này liên hệ với nhau thế nào?**

Không đặt mục tiêu chứng minh “cứ data drift là model giảm chất lượng”. Phải đo hai nhánh độc lập trên cùng cửa sổ W:

```text
Reference R.X + Current W.X → drift detector → drift share, alert
                       W.X → fixed model → prediction
                       W.y + prediction → recall, FPR, macro-F1, FN
                                           ↓
                               so sánh với cửa sổ S0
```

Nhãn thật W.y chỉ dùng chấm điểm bên ngoài detector. Data drift là thay đổi phân phối đầu vào; chất lượng giảm cần bằng chứng từ nhãn thật. Không suy ra concept drift chỉ từ drift share hoặc recall giảm. Đây cũng là giới hạn được giải thích trong [tài liệu monitoring của Evidently](https://www.evidentlyai.com/blog/ml-monitoring-do-i-need-data-drift).

Ba trường hợp phải phân biệt được:

1. **S0:** cùng thành phần traffic với reference; detector và chất lượng ổn định đến mức nào?
2. **S1:** thay tỷ lệ BENIGN/DDoS; có drift nhưng chất lượng có thể vẫn gần mức baseline.
3. **S2:** giữ tỷ lệ attack tổng, tăng các họ attack không được dùng khi train; drift và recall thay đổi ra sao?

Bằng chứng offline trả lời câu hỏi khoa học trong các kịch bản có kiểm soát. Replay service kiểm tra hệ thống có xử lý đúng bằng chứng đó. Replay không biến dữ liệu này thành natural drift hoặc một tập kiểm chứng độc lập.

## 2. Diễn giải review và mức đáp ứng thực tế

Reviewer 1 muốn đánh giá hiệu quả của drift-aware lifecycle thay vì chỉ minh họa prototype bằng controlled splits. Các yêu cầu cần được phân biệt:

| Yêu cầu reviewer 1 | Công việc trong đợt này | Kết luận được phép |
|---|---|---|
| Làm rõ đóng góp khoa học | Rút mô tả architecture; nêu câu hỏi, protocol và bài học về drift alert so với model quality | Đóng góp thiết kế và đánh giá có phạm vi; không tự nhận thuật toán drift mới |
| So sánh lifecycle/retraining strategies | Giữ model cố định để tách drift khỏi thay đổi model; chưa so sánh retraining | **Chưa đáp ứng** so sánh fixed/periodic/drift-triggered retraining |
| Natural/temporal drift | Dùng đúng nguồn và split hiện có, công khai controlled mixtures | **Chưa đáp ứng** natural/temporal drift; không đổi tên S1/S2 thành temporal |
| Sensitivity của drift thresholds | E-D2: ngưỡng, hai window sizes, stable controls; so sánh KS/BH và Evidently | Đáp ứng trực tiếp trong phạm vi dữ liệu đã khóa |
| Nhiều model/tenant/concurrent requests | Không thuộc plan drift này | Replay một model không chứng minh scalability hay multi-model capacity |

Reviewer 2 vẫn có các điểm phải xử lý: provenance, overlap, giới hạn kết quả gần hoàn hảo, khả năng tái lập và citation. Kết quả mới không tự giải quyết citation-integrity trigger chưa được chỉ rõ. Phải rà lại bibliography và không dùng các số liệu này để khẳng định production-readiness.

## 3. Những gì đã có và việc còn lại

| Hạng mục | Trạng thái tại 27/09 | Việc tiếp theo |
|---|---|---|
| E-D1: S0/S1/S2, n=500/1000, 5 sampling seeds | Đã có 70 cửa sổ offline | Giữ nguyên manifest, model và dữ liệu |
| Stable controls bổ sung | Đã có 50 cửa sổ; tổng S0=60 | Dùng cho tỷ lệ cảnh báo trên stable traffic |
| E-D2 KS/BH và replay thư viện Evidently 0.4.15 | Đã có trên 120 cửa sổ | Tổng hợp đối chiếu cùng window; không coi là service benchmark |
| Liên kết drift với suy giảm trên từng window | Đã có số liệu thành phần | Cần bảng phân tích chung, delta so với S0 và hình minh họa |
| Giải thích lỗi theo họ attack trong từng window | Có nhãn/membership để tính | Cần bảng recall/FN theo family và kiểm tra tổng khớp |
| Replay qua toàn bộ service | Chưa có kết quả mới | Bạn phụ trách hệ thống chạy bộ replay ở mục 9 |
| Người thứ hai tái lập bảng chính | Cần thực hiện | Kiểm tra từ model, manifest, dữ liệu và script |

Nguồn kết quả: [experiment README](../../research/paper/experiments/drift_only/README.md), thư mục `results/run_20260926` và `results/evidently_20260927` bên trong cùng thư mục experiment. Không ghi đè các kết quả đã khóa.

## 4. Khóa protocol trước khi phân tích tiếp

### 4.1. Dữ liệu, model và reference

- Dữ liệu đầu vào hiện tại: `data/reference_data.csv`, dẫn xuất từ CIC-IDS2017 qua các bước tiền xử lý/tách nhãn đã mô tả trong artifact. Không trình bày như CSV raw chính thức chưa qua xử lý.
- SHA-256 dữ liệu: `0728925d293f433a3f7bce4509c00e1648906c59c59d8e63663e1622a226ef6c`.
- Audit hiện có: 209865 dòng đầu vào; loại 20 dòng xung đột nhãn có cùng vector feature và 1 duplicate, còn 209844. Kiểm tra dedup hiện tại không chứng minh preprocessing upstream không leakage.
- Split seed 260926; train/dev/reference/evaluation pools lần lượt 50/10/20/20%. Lấy đúng membership đã lưu, không tự chia lại.
- Model `baseline.ubj`: XGBoost đã fit trên BENIGN và DDoS, 74994 dòng; 52 feature; binary ATTACK nếu nhãn gốc khác BENIGN. Không train lại trong phép thử này.
- SHA-256 model: `bd0a91ec11d38ccceca4950a571857f3710bc7034bb8aaf30b40295dfd15e8b5`.
- Reference cố định: 5000 dòng = 3500 BENIGN + 1500 DDoS, không trùng với evaluation pool.
- Nhãn dự đoán: ATTACK nếu P(ATTACK) ≥ 0.5. Giữ thứ tự feature, kiểu dữ liệu và preprocessing như runner gốc.
- Seeds chính: 42, 123, 456, 789, 1024. Seeds S0 bổ sung: 2000–2024 cho mỗi kích thước cửa sổ.

Các seeds thay đổi lấy mẫu cửa sổ, **không phải năm lần train hoặc năm ngày capture độc lập**. Các cửa sổ có thể dùng lại dòng trong evaluation pool; trong một cửa sổ lấy mẫu không hoàn lại. Phải giữ điều này trong limitations.

### 4.2. Bốn ngưỡng khác nhau

| Ngưỡng | Ý nghĩa | Giá trị dùng |
|---|---|---|
| Prediction threshold | Đổi xác suất thành BENIGN/ATTACK | 0.5 |
| KS/BH per-feature | Feature có thay đổi theo kiểm định sau hiệu chỉnh nhiều phép thử | q < 0.05 |
| Evidently per-feature | Ngưỡng của statistic do thư viện chọn | Replay hiện có: 0.1; ghi rõ statistic từng feature |
| Dataset drift share | Tỷ lệ feature drift để phát cảnh báo dataset | KS/BH: 0.3 chính trong baseline; Evidently: 0.6 theo service, 0.3 là đối chiếu |

Evidently replay hiện có chọn 49 normalized Wasserstein và 3 Jensen–Shannon, không phải KS cho tất cả feature. Không so sánh giá trị statistic thô giữa các loại như cùng đơn vị.

## 5. E-D1: chính xác benchmark các kịch bản nào?

### 5.1. Thành phần từng cửa sổ n=1000

| Scenario | BENIGN | DDoS | PortScan | BruteForce | WebAttacks | Thay đổi cần đánh giá |
|---|---:|---:|---:|---:|---:|---|
| S0 | 700 | 300 | 0 | 0 | 0 | Stable control, cùng mixture reference |
| S1_a15 | 850 | 150 | 0 | 0 | 0 | Giảm attack prevalence xuống 15% |
| S1_a50 | 500 | 500 | 0 | 0 | 0 | Tăng attack prevalence lên 50% |
| S1_a85 | 150 | 850 | 0 | 0 | 0 | Tăng attack prevalence lên 85% |
| S2_r25 | 700 | 225 | 25 | 25 | 25 | Thay 25% số attack bằng ba family chưa dùng khi fit |
| S2_r50 | 700 | 150 | 50 | 50 | 50 | Thay 50% số attack |
| S2_r100 | 700 | 0 | 100 | 100 | 100 | Thay toàn bộ số attack |

S2 luôn có 30% attack. r25 là 25% của 300 attack, không phải 25% toàn cửa sổ. n=500 dùng số dòng chính xác từ `window_membership.csv.gz`; runner có làm tròn khi chia ba family, không tự tạo lại bằng cách chia đôi bảng trên.

Chạy/phân tích 7 scenario × 2 kích thước × 5 seeds = 70 cửa sổ chính. Bổ sung 25 S0 mỗi kích thước tạo tổng 120 cửa sổ; S0 có 30 cửa sổ/kích thước khi tính stable alert rate.

### 5.2. S0 — detector có cảnh báo trên traffic ổn định không?

**Đo:** số cảnh báo k/30 tại mỗi n và ngưỡng, drift share, confusion matrix và recall/FPR. Bảng chất lượng chính vẫn dùng 5 seeds để cùng thiết kế với S1/S2; 25 S0 bổ sung báo riêng hoặc ghi rõ tổng 30.

**Đánh giá:** đây là empirical stable-control alert rate trong cách lấy mẫu này. Nếu 0/30, viết “không quan sát cảnh báo trong 30 cửa sổ”, không viết production false-positive rate bằng 0.

### 5.3. S1 — thay distribution có nhất thiết gây suy giảm không?

**Đo:** drift share/alert cùng recall attack, FPR trên BENIGN, macro-F1 và số FN. Đối chiếu S0 cùng n và seed.

**Đánh giá:** S1 chỉ thay prevalence của hai nhãn đã được model học. Nếu detector cảnh báo nhưng recall/FPR vẫn gần baseline, đây là ví dụ data drift không đi kèm suy giảm rõ rệt trong các cửa sổ đo được. Không cần ép model phải giảm để thí nghiệm “thành công”.

Precision/F1 có thể đổi khi prevalence đổi dù conditional error rates gần như giữ nguyên; vì vậy phải đọc recall và FPR cùng F1. Không gọi S1 là pure covariate shift đã được xác minh.

### 5.4. S2 — model bỏ sót loại traffic nào?

**Đo:** recall tổng, FN tổng, recall/FN theo DDoS, PortScan, BruteForce, WebAttacks; giữ FPR BENIGN để biết lỗi đến từ bỏ sót attack hay báo nhầm benign.

**Đánh giá:** tỷ lệ attack tổng giữ nguyên giúp tránh giải thích kết quả chỉ bằng prevalence. Cần chỉ ra các family chưa được dùng khi train đóng góp bao nhiêu FN. Recall tổng tuân theo:

```text
Recall_attack = tổng theo family [ (n_family / n_attack) × Recall_family ]
FN_attack = tổng FN_family
```

Family không có mẫu trong cửa sổ ghi N/A, không ghi recall=0. Recall giảm khi mixture chuyển sang family model nhận diện kém là thay đổi chất lượng trên workload; không có nghĩa trọng số model tự suy thoái theo thời gian, và chưa chứng minh P(Y|X) thay đổi.

## 6. Metric nào cần thu, dùng để đánh giá gì?

| Metric trên mỗi window | Định nghĩa / đơn vị | Dùng để kết luận |
|---|---|---|
| TN, FP, FN, TP | Số dòng, tổng bằng n | Nền kiểm tra mọi metric; FN là attack bỏ sót |
| Attack recall | TP/(TP+FN), khoảng 0–1 | Khả năng bắt attack, chỉ số chất lượng chính |
| Benign FPR | FP/(FP+TN), khoảng 0–1 | Báo nhầm traffic lành tính |
| Macro-F1 | Trung bình F1 hai lớp | Chỉ số bổ sung; không thay recall/FPR |
| Recall/FN theo family | Chấm binary ATTACK trên nhãn gốc từng family | Giải thích nguồn suy giảm ở S2 |
| Drift share | Số feature bị đánh dấu / số feature được đánh giá | Mức phản ứng của detector, không phải % model suy giảm |
| Alert | drift share đạt điều kiện threshold của implementation | Quyết định monitor ở cấu hình đó |
| Alert count | k/5 ở shifted scenario, k/30 ở S0 mở rộng | Độ nhạy theo ngưỡng và biến động lấy mẫu |
| Membership, hashes | Dòng nào vào model/detector và phiên bản nào | Chứng minh hai nhánh chấm cùng dữ liệu |

Với từng window, lấy S0 **cùng n và seed** làm đối chiếu thiết kế:

```text
recall_drop_pp = 100 × (recall_S0 - recall_window)
fpr_increase_pp = 100 × (FPR_window - FPR_S0)
macro_f1_drop_pp = 100 × (macro_F1_S0 - macro_F1_window)
```

Giá trị dương tương ứng chiều xấu đi. Recall từ 1 xuống 0.508 là giảm 49.2 điểm phần trăm. Cùng seed không có nghĩa các scenario chứa cùng từng dòng dữ liệu.

Báo cáo từng window và mean ± SD của 5 seeds cho bảng chính. Đây là biến động lấy mẫu trong một pool, không phải độ bất định giữa các môi trường triển khai. Không coi các dòng/window có overlap là mẫu độc lập để tạo p-value hoặc khoảng tin cậy giả. Không dùng một ngưỡng suy giảm tùy ý sau khi xem kết quả để tuyên bố detector đã được tối ưu. Ưu tiên effect size liên tục và số lỗi thực tế.

## 7. E-D2: sensitivity của drift threshold và window size

Dùng lại drift share đã tính; sweep dataset threshold không cần train lại hoặc tạo dữ liệu mới.

1. Giữ kết quả KS/BH gốc với ngưỡng 0.1, 0.3, 0.5, 0.7.
2. Giữ Evidently 0.6 là cấu hình service cần đánh giá, 0.3 là đối chiếu đã có.
3. Nếu cần heatmap đồng nhất, phân tích bổ sung cả hai detector trên lưới 0.1, 0.3, 0.5, 0.6, 0.7, lưu output mới và ghi là phân tích hậu nghiệm.
4. Với mỗi detector × n × scenario × threshold: ghi mean/SD drift share, k/m cảnh báo, recall/FPR của đúng tập window đó.
5. So sánh detector tại cùng threshold khi muốn đánh giá khác biệt detector; đồng thời báo cấu hình triển khai thực tế riêng. Không gán toàn bộ khác biệt ở KS=0.3 và Evidently=0.6 cho thuật toán.

Các câu cần trả lời: tăng ngưỡng làm bỏ qua scenario nào? n=500 và 1000 khác thế nào? Có cửa sổ recall giảm mạnh nhưng không alert không? Có cửa sổ alert trong khi quality gần baseline không?

Không chọn ngưỡng “tốt nhất” trên toàn bộ 120 cửa sổ rồi gọi đó là kết quả held-out. Nếu chỉ phân tích các ngưỡng này, trình bày sensitivity; muốn đề xuất policy tối ưu cần calibration/validation tách riêng.

## 8. Kết quả hiện có: mốc đối chiếu, không phải kết quả service

Bảng dưới lấy **n=1000, 5 seeds chính**; chưa phải kết quả mới qua hệ thống. FPR là tỷ lệ 0–1, FN là trung bình số attack bị bỏ sót mỗi cửa sổ.

| Scenario | Macro-F1 trung bình | Recall attack | FPR benign | FN trung bình | Evidently alert ở 0.6 |
|---|---:|---:|---:|---:|---:|
| S0 | 1.000000 | 1.000000 | 0.000000 | 0.0 | 0/5 |
| S1_a15 | 1.000000 | 1.000000 | 0.000000 | 0.0 | 0/5 |
| S1_a50 | 1.000000 | 1.000000 | 0.000000 | 0.0 | 0/5 |
| S1_a85 | 0.999216 | 0.999765 | 0.001333 | 0.2 | 5/5 |
| S2_r25 | 0.904554 | 0.753333 | 0.000000 | 74.0 | 0/5 |
| S2_r50 | 0.789178 | 0.508000 | 0.000000 | 147.6 | 0/5 |
| S2_r100 | 0.422355 | 0.010000 | 0.000000 | 297.0 | 1/5 |

Hai đối chiếu đáng đưa vào paper nếu tái kiểm tra khớp artifact:

- S1_a85: 5/5 alert nhưng chất lượng gần baseline trong các cửa sổ này.
- S2_r50: recall trung bình còn 0.508, nhưng Evidently ở ngưỡng 0.6 không alert trong 5 cửa sổ. Cảnh báo phân phối không phải một phép đo trực tiếp độ suy giảm.

Đây là phát hiện có ích, không phải lỗi cần sửa số liệu. Kiểm tra threshold và statistic giải thích tại sao xảy ra; không thay cấu hình sau khi xem test rồi bỏ kết quả cũ. Các điểm số cao ở S0/S1 chỉ phản ánh workload BENIGN/DDoS đã chọn, không chứng minh NIDS tổng quát tốt trên mọi attack.

## 9. Việc giao bạn phụ trách hệ thống: replay để xác minh luồng drift

### 9.1. Bộ replay nhỏ nhưng trả lời đúng câu hỏi

Chọn S0, S1_a85, S2_r50, S2_r100; n=1000; seeds 42, 123, 456. Tổng **12 window replays, 12000 lượt inference hợp lệ**, dùng cùng model và reference. Đây không phải 12 cấu hình benchmark tải.

Bắt đầu với 4 scenario ở seed 42. Nếu audit dữ liệu/parity đạt mới mở rộng hai seeds còn lại. Nếu chỉ hoàn thành 4, báo đúng 4 và coi là kiểm tra tích hợp giới hạn. Không thay số lần chạy bằng số request để tăng cỡ mẫu nghiên cứu.

### 9.2. Gói dữ liệu giao trước khi chạy

**Đã bổ sung công cụ bàn giao:** xem [HANDOFF_VI.md](../../research/paper/experiments/drift_only/HANDOFF_VI.md). Sau khi pull nhánh, chạy `export_handoff.py --with-mlflow` theo hướng dẫn để xuất đúng reference/12 windows từ dataset đã có. Script kiểm tra checksum nguồn, dự đoán offline và bản đóng gói MLflow; không tự chạy benchmark qua service.

Người phụ trách thực nghiệm xuất từ frozen membership:

- Một reference CSV chỉ gồm 52 feature và manifest/hash.
- Một file input/window gồm 1000 dòng feature đúng thứ tự, kèm row ID ở sidecar.
- Sidecar nhãn thật, family, expected prediction và liên kết row ID; không đưa nhãn/ID vào feature detector.
- Model artifact và cấu hình inference; output kỳ vọng offline và Evidently library replay cùng window.
- Manifest scenario, seed, n, hashes, feature list, detector version và thresholds.

Đóng gói model vào worker phải giữ nguyên dự đoán của artifact gốc; không thay bằng model production đang có chỉ vì cùng tên XGBoost.

### 9.3. Trình tự cho mỗi window

1. **Cô lập dữ liệu replay:** dùng model-version/namespace dữ liệu sạch dành cho window theo cơ chế hệ thống hỗ trợ. Code đọc các production rows mới nhất theo version, không mặc nhiên biết ranh giới scenario. Không gửi nối S0 → S1 → S2 vào một version rồi giả định report chỉ có window cuối.
2. Gắn đúng reference, xác nhận hash; không dùng fallback lấy một phần production làm reference. Mọi smoke request phải ở version riêng hoặc được loại khỏi tập đầu vào có bằng chứng.
3. Gửi đúng 1000 dòng với tốc độ vừa phải, giữ ánh xạ row ID → request ID → prediction ID. Lưu response, prediction và xác suất nếu API cung cấp. Không benchmark concurrency.
4. Chờ consumer lưu đủ đúng 1000 production samples. Đối chiếu tập ID và feature với input, kiểm tra thiếu/trùng/sai scope. Request lỗi hoặc retry có thể làm lệch tập; không chỉ lấy 1000 dòng bất kỳ và gọi là đủ.
5. Kiểm tra drift run dùng đúng window và 5000 reference rows. Phân biệt **sample-count trigger** với **dataset drift threshold=0.6**. Nếu auto-trigger không đọc đúng tập đã khóa, chạy report có kiểm soát/manual và ghi đúng trigger mode; không tuyên bố đã kiểm chứng auto-trigger.
6. Xuất report JSON/summary và danh sách các feature thực sự được đánh giá. Chỉ so với offline khi cùng 52 input features. Nếu prediction/Label/ID lọt vào report, đánh dấu không tương đương và sửa cấu hình hoặc tách kết quả; không âm thầm so drift share khác mẫu số.
7. Join dự đoán API với sidecar nhãn thật để chấm recall/FPR/F1/FN. Nhãn không lấy từ dự đoán model và không được detector sử dụng.
8. Lưu run ID, model-version UUID, input/reference/model hashes, image digest, phiên bản thư viện, membership audit, report và trạng thái callback. Ghi lại sai lệch kể cả khi kết quả khác offline.

### 9.4. Tiêu chí hoàn thành một replay hợp lệ

| Kiểm tra | Điều kiện / cách xử lý |
|---|---|
| Input coverage | Đúng tập 1000 ID; không mất/trùng dòng; feature khớp input |
| Reference | Đúng tập 5000 dòng/hash, không overlap evaluation |
| Inference parity | Nhãn dự đoán khớp từng dòng và confusion matrix khớp; nếu sai phải điều tra artifact/feature/preprocessing |
| Detector parity | Cùng membership, columns, version, statistic và thresholds; drift flags/alert khớp hoặc giải thích sai khác |
| Report ownership | Đúng version/run, callback thành công, report truy xuất được |
| Failure accounting | Liệt kê request/log/report lỗi; cửa sổ thiếu dữ liệu không được dùng như một phép đo đầy đủ |

Nếu xác suất floating-point khác, ghi max absolute difference và định trước tolerance theo runtime trước khi đánh giá parity. Không sửa tolerance để che nhãn dự đoán khác. Với statistic khác dependency/version, báo khác cấu hình thay vì ép số bằng nhau.

Prometheus/Grafana chỉ hỗ trợ tìm lỗi request, consumer hoặc drift job và xác định thời điểm chạy. CPU/RAM/HTTP latency không chứng minh model suy giảm. Bằng chứng chính là ID/membership, dự đoán có nhãn thật và report drift. Không cần đưa dashboard tải vào paper cho mục tiêu này.

## 10. Phần phân tích offline cần làm tiếp

### A1 — Bảng chung drift và quality, bắt buộc

Join `window_metrics.csv` với `window_comparison.csv` bằng định danh cửa sổ, kiểm tra quan hệ một-một trước khi mở rộng theo detector/threshold. Tính delta so với S0; xuất một bảng chứa cả drift và quality cho mỗi window. Kiểm tra tổng confusion matrix=n và số attack/benign đúng protocol.

### A2 — Giải thích theo family, bắt buộc

Từ `window_membership.csv.gz`, nhãn gốc và model cố định, tạo `family_metrics.csv`: window, family, support, TP_attack, FN_attack, recall. Tính lại tổng FN/recall từ family và đối chiếu A1. Dùng đúng window để giải thích S2, không lấy chẩn đoán trên toàn evaluation pool thay cho số liệu window.

Kết quả whole-pool diagnostics đã có chỉ dùng giải thích hậu nghiệm, không phải tập kiểm chứng độc lập. Nếu chạy lại inference để xuất family metrics, dùng cùng artifact và không fit thêm bất kỳ bước nào.

### A3 — Tách từng family, chỉ làm nếu còn thời gian

Nếu A2 chưa đủ rõ, có thể thêm 3 kịch bản n=1000: 700 BENIGN + 150 DDoS + 150 mẫu của lần lượt PortScan, BruteForce hoặc WebAttacks; 5 seeds → 15 cửa sổ. Gọi là phân tích bổ sung hậu nghiệm theo family, không gọi là S3 vì **S3 trong plan gốc dành cho temporal/capture shift**.

Đây vẫn là cùng evaluation pool; WebAttacks có ít mẫu và các lần lấy mẫu sẽ overlap. Không gọi là xác nhận độc lập. Ưu tiên A1/A2 và replay đúng dữ liệu hơn A3; không bắt buộc mở rộng thí nghiệm trước hạn nộp.

## 11. Paper cần bảng/hình gì, mỗi cái chứng minh gì?

| Đầu ra | Nội dung cần có | Vai trò trong paper |
|---|---|---|
| Bảng 1: protocol | Mixture S0/S1/S2, model train labels, reference, n, seeds, split/provenance | Người đọc hiểu chính xác tác động được tạo ra |
| Bảng 2: kết quả chính | 7 scenario ở n=1000; recall/FPR/macro-F1 mean ± SD; FN; drift share và alert của từng detector/cấu hình | So sánh data shift với quality; tránh chỉ báo accuracy |
| Hình 1: drift–quality | Trục x drift share, y attack recall; mỗi điểm một window; màu theo scenario, tách panel detector; vạch threshold | Thấy alert nhưng recall cao, và recall thấp nhưng chưa alert; không nối thành timeline |
| Hình 2 / supplement: sensitivity | Heatmap alert k/m theo scenario × threshold, tách n và detector; S0 m=30, shifted m=5 | Vì sao threshold/window size ảnh hưởng quyết định |
| Bảng 3 / supplement: family errors | Support, recall, FN từng family; tổng khớp bảng chính | Giải thích S2 suy giảm từ nhóm attack nào |
| Bảng 4 nếu replay xong | Số window hợp lệ, input/log coverage, prediction/report parity, lỗi thực tế | Kiểm chứng luồng hệ thống trên cùng dữ liệu; không chứng minh scalability |

Short paper ưu tiên Bảng 1–2 và Hình 1; thu nhỏ phần architecture để dành chỗ cho protocol, kết quả và limitations. Chi tiết threshold/family/per-window đưa vào artifact nếu vượt giới hạn trang đã được BTC xác nhận. Không tạo bảng service toàn số “pass” khi chưa chạy.

## 12. Cách diễn giải các kết quả có thể gặp

| Drift alert | Quality so với S0 | Cách viết kết luận |
|---|---|---|
| Có | Gần baseline trong các cửa sổ đo | Monitor phát hiện thay đổi phân phối nhưng thay đổi đó chưa đi kèm suy giảm rõ; không gọi là false drift alarm chỉ vì model vẫn tốt |
| Có | Recall giảm/FPR tăng | Thay đổi dữ liệu đi kèm suy giảm trên workload đó; cần nhãn để xác nhận |
| Không | Recall giảm/FPR tăng | Cấu hình detector hiện tại không cảnh báo một số cửa sổ có chất lượng thấp; không kết luận dữ liệu không shift |
| Không | Gần baseline | Kết quả ổn định trong cửa sổ đo; không bảo đảm không có loại shift khác |

Không dùng scatter hoặc correlation để tuyên bố drift gây ra degradation nói chung. Thí nghiệm này can thiệp có kiểm soát vào thành phần traffic, quan sát phản ứng của một model cố định; chưa mô phỏng đầy đủ production hay chứng minh concept drift. Chấm điểm dùng ground truth retrospective; production không có nhãn thì chưa thể suy ra recall từ drift share.

## 13. Lộ trình tiếp nối tuần 24–30/09

Không khởi động lại một tuần mới; phần offline đã làm được giữ nguyên. Các thời lượng dưới đây là dự kiến phân công, không phải thời gian chạy đã đo.

| Mốc | Người phụ trách ML/paper | Người phụ trách hệ thống | Điều kiện chốt |
|---|---|---|---|
| 27/09, đầu việc 1 (1–2 giờ) | Kiểm tra frozen artifact; xuất A1 và gói 4 window seed 42 | Nhận manifests và xác định cách cô lập production window | Cùng model/reference/inputs, không tạo split mới |
| 27/09, đầu việc 2 (2–3 giờ) | Làm A2, kiểm tra tổng FN/recall; dựng bảng/hình | Replay 4 window đầu, audit IDs và parity | Có bundle đầy đủ cho từng window hoặc lỗi được ghi rõ |
| Cuối 27 – sáng 28/09 | Hoàn thiện sensitivity và caption/limitations | Nếu pilot đạt, mở rộng 12 window; nếu không, ưu tiên sửa lệch dữ liệu | Đóng băng cấu hình và số lượt thực sự hoàn tất |
| 28/09 | Viết Results/Discussion, rút architecture, cập nhật response reviewer | Giao raw reports + summary, không chỉ screenshot | Từng câu khẳng định gắn với số liệu có thật |
| 29/09 | Người thứ hai tái tạo bảng; rà citations, nguồn dữ liệu, compile LaTeX | Hỗ trợ tái kiểm tra các mismatch còn lại | Bảng, CSV, hình và manuscript nhất quán |
| 30/09 | Chốt metadata/forms, kiểm tra file nộp và nộp theo hướng dẫn BTC | Không mở rộng scope sát hạn | Không thêm kết quả chưa kiểm chứng |

Nếu service không hoàn thành kịp, dùng gói offline đã xác minh và ghi rõ giới hạn tích hợp. Không thay bằng số liệu suy đoán. Bỏ A3 trước; không cắt audit membership, kiểm tra citations hoặc kiểm chứng bảng chính để đổi lấy thêm scenario.

## 14. Artifact phải giao để bạn khác kiểm tra

Tạo thư mục kết quả mới, ví dụ `drift_performance_followup_YYYYMMDD/`, gồm:

```text
protocol.json                  # model/data/reference hashes, seeds, thresholds
window_analysis.csv            # drift và quality trên cùng window
family_metrics.csv             # support, TP/FN, recall từng family
threshold_analysis.csv         # detector × window × threshold, alert
service_replay/                # chỉ có khi thực sự replay
  <window_id>/                 # manifests, requests, row mapping, DB audit, report
  parity_summary.csv
figures/
tables/
README.md                      # lệnh tái lập, versions, limitations, trạng thái
```

Các cột tối thiểu của bảng phân tích: `window_id, scenario, n, seed, detector, threshold, drift_share, alert, tn, fp, fn, tp, recall, fpr, macro_f1, recall_drop_pp, fpr_increase_pp`. Bảng long format có nhiều dòng detector/threshold cho một window; khi thống kê số thí nghiệm phải đếm unique window, không đếm tất cả dòng như các lần chạy độc lập.

Checklist giao kết quả:

- Model/reference giữ nguyên; không có training, tuning hoặc chọn ngưỡng bí mật trên test.
- Label/family/ID không lọt vào input features của model/detector.
- Reference/evaluation disjoint; khai báo overlap giữa các evaluation windows.
- Counts, metric, family decomposition và hashes kiểm tra được từ artifact.
- Số alert có mẫu số; số quality có đơn vị; bảng chính và stable controls không trộn lẫn seeds.
- Kết quả offline, library replay và service replay phân biệt rõ.
- Báo cáo mismatch/failed windows, không chỉ giữ kết quả thuận lợi.
- Không gọi controlled sampling là temporal drift; không khẳng định concept drift hoặc hiệu quả retraining.

## 15. Đoạn giao việc ngắn cho bạn trong nhóm

> Mình tiếp tục đúng plan one_week_drift_plan, giữ NIDS và model cố định. Offline đã có S0 ổn định, S1 đổi tỷ lệ benign/attack và S2 tăng các family chưa dùng khi train. Mình sẽ tổng hợp drift với recall/FPR trên cùng window và phân tích FN theo family. Bạn giúp replay 4 scenario S0, S1_a85, S2_r50, S2_r100 qua hệ thống, trước hết seed 42 rồi mở rộng 3 seeds nếu dữ liệu khớp. Mỗi window 1000 request; cần kiểm tra đúng mẫu được lưu, đúng reference, drift report và prediction so với offline. Mục tiêu là chỉ ra khi nào distribution đổi nhưng model vẫn tốt, khi nào model bỏ sót nhiều attack và detector có cảnh báo được không. Đây là kiểm chứng luồng drift, chưa phải benchmark tải hay retraining.
