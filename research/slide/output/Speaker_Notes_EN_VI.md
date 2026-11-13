## 1. A Drift-Aware MLOps Framework
for Multi-Model Serving

Thời gian: 20 giây

### English
Good morning. I am Hoang Tran-Nguyen-Viet from the University of Information Technology, VNU-HCM. Today I will present our drift-aware MLOps framework for multi-model serving, using network intrusion detection as a case study.

### Tiếng Việt
Giới thiệu tên, đơn vị và tên nghiên cứu. Trọng tâm là framework MLOps và cách diễn giải bằng chứng drift, không phải đề xuất một thuật toán phân loại mới.

Transition: I will begin with the monitoring problem that motivates this work.

Source: Paper CSoNet

## 2. Distribution alerts and predictive quality

Thời gian: 50 giây

### English
Once we deploy a model, the input distribution can change. A distribution monitor compares current features with a reference and can raise an alert before labels become available. Predictive quality answers a different question: does the model still recognize attacks? We need labels to measure that outcome. In intrusion detection, the distinction matters because missed attacks can increase even when a dataset-level drift alert remains absent. Our study asks whether these signals agree under controlled shifts, and how an MLOps framework should preserve their context for review.

### Tiếng Việt
Drift kiểm tra thay đổi phân phối đầu vào, còn recall kiểm tra khả năng phát hiện attack. Chất lượng cần nhãn, có thể chỉ biết sau. Không xem việc không có cảnh báo drift là bằng chứng chất lượng ổn định.

Transition: This distinction defines both our framework and our evaluation.

Source: Paper CSoNet

## 3. Study scope and contributions

Thời gian: 40 giây

### English
Our work has a framework contribution and an empirical contribution. The framework associates each model version with its reference data and monitoring reports through a PostgreSQL-backed Native Registry. The evaluation examines distribution alerts alongside labeled quality under controlled traffic mixtures. We also report a service replay that exercises the integration path. The architecture targets multi-model serving, while the quantitative study deliberately holds one XGBoost classifier fixed. This design isolates changes in the evaluation windows rather than changes introduced by retraining.

### Tiếng Việt
Phân biệt khả năng kiến trúc và phạm vi đã đo. Multi-model là phạm vi thiết kế, không phải kết quả benchmark nhiều mô hình đồng thời. Giữ model cố định để quan sát ảnh hưởng của dữ liệu.

Transition: Let us look at where the monitoring evidence belongs in the framework.

Source: Paper CSoNet

## 4. Framework architecture

Thời gian: 65 giây

### English
The framework separates lifecycle coordination from prediction execution. The control plane manages model metadata and deployment context. A serving gateway routes inference requests to the appropriate worker. An asynchronous logging path carries production records to persistence, where monitoring can construct windows without placing the full analysis inside the prediction request. The Native Registry maintains the associations between a model version, its reference and its reports. Those associations matter when several versions or models exist: an operator must know which model and reference produced the evidence. The evaluated prototype demonstrates this integration path. The study does not establish throughput, tenant-isolation guarantees or scalability under concurrent multi-model workloads.

### Tiếng Việt
Khi bổ sung hình, diễn giải theo các plane và quyền sở hữu trạng thái. Native Registry lưu liên kết phiên bản, reference và report. Đường logging bất đồng bộ tách xử lý monitoring khỏi request inference. Không suy ra độ trễ thấp hoặc khả năng mở rộng khi chưa benchmark.

Transition: Within this architecture, monitoring produces evidence for a review workflow.

Source: Paper CSoNet

## 5. Monitoring and review workflow

Thời gian: 65 giây

### English
A monitoring run selects production records for a window and compares them with the reference associated with the model version. The resulting report records distribution evidence. When matched ground-truth labels are available, a separate evaluation can measure attack recall and other quality metrics. An operator can then review the distribution signal together with labeled quality and the relevant version context. Missing labels leave quality unknown. Our experiments supply labels in the evaluation layer, but do not demonstrate automatic production labeling. Likewise, the review contract describes how update decisions should use evidence. We have not evaluated an automatic adaptation policy or shown that a retrained model restores quality.

### Tiếng Việt
Phân biệt đường monitor đã triển khai và bước quyết định cập nhật đề xuất. Nhãn dùng trong evaluation không có nghĩa hệ thống tự tạo ground truth trong production. Nếu thiếu nhãn thì chất lượng chưa biết.

Transition: The following experiments examine this distinction with a fixed model and controlled inputs.

Source: Paper CSoNet

## 6. Data and fixed-model setup

Thời gian: 60 giây

### English
We use a processed derivative of CICIDS2017 with 209,844 retained rows and 52 numeric features. We separate training, development, reference and evaluation pools in proportions of fifty, ten, twenty and twenty percent. The reference contains a fixed sample of five thousand rows. The classifier learns BENIGN and DDoS, while PortScan, BruteForce and WebAttacks provide held-out attack families for the replacement experiment. We check that the pools share no exact feature vectors. This check does not establish independence between sessions or correlated flows. The processed derivative also lacks the temporal identifiers needed for a chronological validation.

### Tiếng Việt
BENIGN/DDoS là các nhãn model học. PortScan, BruteForce, WebAttacks là các họ giữ lại cho S2. Không nhầm pool reference 20% với mẫu reference thực dùng 5.000 dòng. Zero exact overlap chỉ là kiểm tra trùng vector.

Transition: We construct two types of shift from these evaluation pools.

Source: Paper CSoNet

## 7. Controlled shift scenarios

Thời gian: 60 giây

### English
The stacked columns show input composition rather than prediction outcomes. S0 is the stable baseline with thirty percent attacks. S1 changes attack prevalence to fifteen, fifty or eighty-five percent, while keeping the learned attack family. S2 keeps total attack prevalence at thirty percent but replaces a fraction of DDoS rows with held-out families. Importantly, the replacement percentage refers to attack rows. At twenty-five percent replacement in a thousand-row window, we have seven hundred benign rows, two hundred and twenty-five DDoS rows, and seventy-five held-out attacks. This separates a change in prevalence from a change in attack composition.

### Tiếng Việt
Đọc chart theo thành phần mẫu. S1-a15 nghĩa attack chiếm 15% tổng cửa sổ. S2-r25 nghĩa thay 25% nhóm attack, tương ứng 7.5% toàn cửa sổ. Không gọi các cột là diễn biến theo thời gian.

Transition: We apply the same offline monitoring protocol to these windows.

Source: Paper CSoNet

## 8. Evaluation protocol

Thời gian: 65 giây

### English
For each window, we run two-sided Kolmogorov–Smirnov tests on all fifty-two features and apply Benjamini–Hochberg correction at alpha zero point zero five. Drift share is the fraction of flagged features. The principal dataset alert threshold is zero point three, retained in advance rather than selected from the outcomes. We also examine thresholds of zero point one, zero point five and zero point seven. The study contains one hundred and twenty windows across sizes of five hundred and one thousand. Five principal seeds generate each shifted setting. Additional stable draws provide thirty S0 windows per size. These draws reuse a fixed model and evaluation pool.

### Tiếng Việt
Alpha 0.05 áp dụng kiểm định feature. Ngưỡng 0.30 áp dụng tỷ lệ feature bị đánh dấu sau BH. Five seeds là năm cửa sổ lấy mẫu, không phải năm lần huấn luyện độc lập. Nhãn không đi vào detector drift.

Transition: First, consider changes in attack prevalence.

Source: Paper CSoNet

## 9. Strong drift with stable quality

Thời gian: 85 giây

### English
Here we show the five principal windows at size one thousand. Circles represent individual windows and diamonds represent means. The left chart shows drift share with the principal alert threshold in red. The right chart shows attack recall in teal and macro-F1 in gray. As attack prevalence changes, the distribution signal becomes strong. At eighty-five percent attacks, the mean drift share is approximately ninety-eight percent. Yet attack recall and macro-F1 remain close to one. The classifier still recognizes the attack family it learned. A distribution alert therefore identifies a change requiring interpretation, but its magnitude alone does not describe the predictive damage. The stable comparison here uses the five principal draws. Small errors occur in some additional stable draws, so perfect values should not be generalized to every S0 window.

### Tiếng Việt
Chỉ vào drift chart rồi quality chart. Các điểm gần nhau ở chất lượng vẫn cần giữ đủ. Không nói S0 luôn hoàn hảo vì bảng heatmap dùng toàn bộ 30 S0, còn chart chính chỉ dùng 5 seed. S1 thay đổi prevalence nhưng vẫn dùng DDoS.

Transition: The replacement experiment produces a different relationship between drift and quality.

Source: Paper CSoNet

## 10. Recall loss with few alerts

Thời gian: 90 giây

### English
S2 changes the attack families while holding total attack prevalence constant. At twenty-five percent replacement, held-out attacks occupy only seven point five percent of the full window. Mean attack recall falls to seventy-five point three three percent, while the detector raises an alert in only one of five windows at the principal threshold. This illustrates how a substantial loss within the attack class can coexist with infrequent dataset alerts. At full replacement, mean recall falls to one percent. We should interpret the decline as a mixture effect: poorly recognized held-out families replace DDoS samples. The experiment does not demonstrate that the fixed model forgets DDoS over time. Comparing this slide with S1 also shows that similarly high drift shares can accompany very different quality outcomes. Drift share cannot rank predictive harm in these cases.

### Tiếng Việt
Nhấn mạnh 75.33% recall và 1/5 cửa sổ có alert. 1/5 là số quan sát nhỏ, không phải xác suất tổng quát. S2-r100 recall còn 1%. Không diễn giải đây là catastrophic forgetting hay một chuỗi production theo thời gian.

Transition: We next examine how thresholds and window sizes affect alert counts.

Source: Paper CSoNet

## 11. Threshold and window-size sensitivity

Thời gian: 70 giây

### English
Each cell reports the number of windows that raise an alert, divided by the number examined. Both tables use the same color scale. The stable setting has thirty windows per size, whereas each shifted setting has five. Stronger shifts trigger alerts across many configurations. The difficult S2-r25 setting remains less sensitive. At size one thousand, lowering the threshold from zero point three to zero point one increases the count from one to two alerts out of five. At the same time, these small controlled samples do not identify a universally optimal threshold. The table supports examining sensitivity explicitly and interpreting the alert alongside quality evidence.

### Tiếng Việt
Đọc ô dưới dạng alerts/windows, không phải feature count. S0 mẫu số 30, shifted mẫu số 5. Nêu ví dụ S2-r25 ở n=1.000. Không tuyên bố ngưỡng 0.10 là tốt nhất từ kết quả này.

Transition: The service replay provides a separate view of system integration.

Source: Paper CSoNet

## 12. Controlled service replay

Thời gian: 70 giây

### English
The service replay reports four thousand-row windows with seed forty-two and a dataset threshold of zero point six. The left chart shows flagged features as a share of fifty-two features. The right chart shows attack recall. Only the S1 eighty-five-percent setting exceeds the service threshold, while the two replacement settings show clear recall loss. These results come from the manuscript's reported service table. Raw service exports are unavailable in this checkout. The service uses an Evidently preset whose tests differ from offline KS with BH correction, so the two sections answer different evaluation questions. The replay exercises prediction, persistence and monitoring integration. It does not establish uptime or throughput guarantees.

### Tiếng Việt
Số liệu service từ bảng paper: flagged feature 1,43,22,29 trên 52 và recall 1,1,0.5067,0.01. Ngưỡng 0.60 chỉ dành drift. S1 từng có 42 lỗi HTTP 502/503 và recovery, không biến pilot thành chứng minh độ tin cậy production.

Transition: The application view provides the context needed to inspect these reports.

Source: Paper CSoNet

## 13. Model-version monitoring in the application

Thời gian: 60 giây

### English
This application view is intended to show the monitoring report beside its model-version context. The important relationship is between the report, the version and the selected reference. An operator needs that relationship to interpret a signal and compare evidence consistently. Distribution results describe the input window. Labeled quality, when available, adds information about missed attacks. The workflow supports a review that considers both kinds of evidence before proposing an update. Our service study checks the integration path, while the controlled experiments explain why these signals should be read together. The effectiveness of the eventual update decision remains a separate evaluation question.

### Tiếng Việt
Sau khi bổ sung ảnh, chỉ vào các trường thực sự xuất hiện: model version, reference và monitoring report. Chất lượng có nhãn được tính ở evaluation layer, không khẳng định screenshot có live quality nếu UI không có. Không đọc tên nút hoặc field chưa có ảnh.

Transition: These results have several limits that define the scope of our conclusions.

Source: Paper CSoNet

## 14. Scope and limitations

Thời gian: 50 giây

### English
The dataset is a processed derivative with uncertain upstream lineage, and missing temporal identifiers limit chronological analysis. Exact feature-vector separation does not rule out correlated flows. The evaluation uses one model, one reference and a limited number of shifted draws, so the observed alert counts should not become broad detection guarantees. The system evidence comes from a pilot integration exercise. We have not benchmarked scalability, verified tenant isolation under adversarial workloads or evaluated the effectiveness of an update policy. These limitations still allow a focused conclusion about the disagreement between distribution alerts and labeled quality in the controlled cases.

### Tiếng Việt
Nêu giới hạn thẳng và ngắn. Phân biệt ý nghĩa thực nghiệm trong các trường hợp có kiểm soát với claim phổ quát về detector hay hệ thống. Đây là giới hạn của bằng chứng đã có.

Transition: I will close with the implications for monitoring and review.

Source: Paper CSoNet

## 15. Conclusions

Thời gian: 50 giây

### English
The controlled experiments show that strong distribution drift can coexist with stable measured quality. They also show that attack recall can decline while dataset alerts remain infrequent. Our framework preserves model-version context so that operators can review distribution reports together with labeled quality when labels become available. The evidence supports that joint interpretation in the studied cases. Future work should evaluate broader data, operational performance and reviewed update policies, including whether updates actually improve outcomes. We acknowledge support from the Scientific Research Fund of VNUHCM-University of Information Technology. Thank you for your attention, and I welcome your questions.

### Tiếng Việt
Kết luận đủ ba ý, không thêm claim tự động thích nghi. Nhắc đóng góp liên kết ngữ cảnh và cách đọc bằng chứng. Cảm ơn quỹ nghiên cứu đúng paper.

Transition: I welcome your questions.

Source: Paper CSoNet

## 16. Questions

Thời gian: 0 giây

### English
Thank you. I welcome questions about the framework, the evaluation protocol or the interpretation of the results.

### Tiếng Việt
Dừng để nhận câu hỏi. Có thể mở các slide phụ lục về workflow hoặc chi tiết protocol.

Transition: 

Source: Paper CSoNet

## 17. Selected references

Thời gian: 0 giây

### English
These references provide background on dataset shift, MLOps architecture, the intrusion dataset, XGBoost and multiple testing.

### Tiếng Việt
Phụ lục tài liệu tham khảo. Tên rút gọn để dễ đọc. Chi tiết đầy đủ nằm trong bibliography của paper.

Transition: 

Source: Paper CSoNet

## 18. Build and deployment workflow

Thời gian: 0 giây

### English
This workflow provides implementation context for packaging and deployment. It is separate from the controlled drift experiment and should not be interpreted as a deployment performance benchmark.

### Tiếng Việt
Bổ sung sơ đồ build-deploy đã sửa theo code. Nếu hỏi về GitOps/K3s, phân biệt đường triển khai từng thực hiện với các đặc tính chưa benchmark.

Transition: 

Source: Paper CSoNet

## 19. Training workflow

Thời gian: 0 giây

### English
The platform includes training lifecycle support. The reported experiment keeps the evaluated classifier fixed, so the results do not measure the benefit of retraining or model promotion.

### Tiếng Việt
Sơ đồ training minh họa khả năng hệ thống. Không dùng để khẳng định đã đánh giá vòng retraining tự động.

Transition: 

Source: Paper CSoNet

## 20. Additional experimental details

Thời gian: 0 giây

### English
The main result charts use five principal seeds. Sensitivity tables include all thirty stable windows per size. The windows may reuse the evaluation pool and are not independent model fits. Offline and service configurations differ. The service results are reported manuscript evidence rather than raw exports or a new cluster measurement.

### Tiếng Việt
Dùng khi hỏi độ độc lập, mẫu số hay khác biệt service/offline. Không thay số liệu service bằng offline Evidently library replay.

Transition: 

Source: Paper CSoNet
