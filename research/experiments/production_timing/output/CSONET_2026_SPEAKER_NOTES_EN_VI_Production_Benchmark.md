# CSoNet 2026 — Bài thuyết trình tiếng Anh và giải thích tiếng Việt

## Cách sử dụng

Đọc phần **English script** khi thuyết trình. Lời nói sử dụng văn phong hội nghị tự nhiên, có câu chuyển ý và giải thích kết quả trong bối cảnh vận hành MLOps. Phần tiếng Việt giúp hiểu ý và thuật ngữ trước khi tập nói. Các câu tiếng Anh được tách dòng để dễ theo dõi. Speaker Notes trong PowerPoint có cùng nội dung.

Lịch nói dự kiến **14 phút 35 giây**, dành **25 giây dự phòng** trong phần trình bày 15 phút. Sau đó có **5 phút phản biện**. Tốc độ trung bình khoảng 98 từ/phút. Hãy dừng ngắn sau mỗi ý và dùng thời gian chỉ sơ đồ. Các mốc thời gian là mục tiêu tập dượt, cần điều chỉnh theo tốc độ nói thực tế.

Trong PowerPoint, mở **View → Notes** để đọc ghi chú, hoặc bật **Presenter View** khi trình chiếu. Điều chỉnh kích thước chữ trong vùng ghi chú theo nhu cầu.

## Thời gian từng slide

| Slide | Nội dung | Thời lượng | Mốc trong bài |
|---|---|---|---|
| 1 | Title | 25 giây | 00:00–00:25 |
| 2 | Distribution Alerts and Predictive Quality | 55 giây | 00:25–01:20 |
| 3 | Scope and Core Contributions | 35 giây | 01:20–01:55 |
| 4 | Presentation Outline | 15 giây | 01:55–02:10 |
| 5 | MLOps Framework | 7 giây | 02:10–02:17 |
| 6 | Architecture Overview | 75 giây | 02:17–03:32 |
| 7 | Build, Register and Deploy a Model Version | 65 giây | 03:32–04:37 |
| 8 | Prediction Logging and Drift Monitoring | 65 giây | 04:37–05:42 |
| 9 | Training Execution Workflow | 65 giây | 05:42–06:47 |
| 10 | NIDS XGBoost Case Study | 7 giây | 06:47–06:54 |
| 11 | Dataset Curation and Fixed-Model Baseline | 50 giây | 06:54–07:44 |
| 12 | Controlled Shift Scenarios | 45 giây | 07:44–08:29 |
| 13 | Monitoring Protocol | 45 giây | 08:29–09:14 |
| 14 | Finding 1: Strong Drift with Stable Quality | 50 giây | 09:14–10:04 |
| 15 | Finding 2: Recall Loss with Few Alerts | 50 giây | 10:04–10:54 |
| 16 | Drift Share and Predictive Harm | 40 giây | 10:54–11:34 |
| 17 | Threshold and Window-Size Sensitivity | 45 giây | 11:34–12:19 |
| 18 | Controlled Service Replay | 55 giây | 12:19–13:14 |
| 19 | Summary | 6 giây | 13:14–13:20 |
| 20 | Conclusions | 40 giây | 13:20–14:00 |
| 21 | Scientific Limitations | 30 giây | 14:00–14:30 |
| 22 | Thank You and Questions | 5 giây | 14:30–14:35 |
| 23 | References | Backup / khi được hỏi | Trong phần phản biện |


## Slide 1 — Title

**Thời gian** — 25 giây, mốc 00:00–00:25.

### English script

> Good morning, everyone. My name is Hoang, and I am from the University of Information Technology in Vietnam.<br>
> Today, I will present our drift-aware MLOps framework for multi-model serving, using network intrusion detection as a case study.<br>

### Giải thích tiếng Việt

Chào khán giả, giới thiệu tên và đơn vị. Bài trình bày tập trung vào khung MLOps và cách liên kết vận hành mô hình với bằng chứng giám sát. Phát hiện tấn công mạng là bài toán dùng để đánh giá hệ thống.

### Gợi ý trình bày

Pause after your name and the presentation topic. Point to the paper title.


## Slide 2 — Distribution Alerts and Predictive Quality

**Thời gian** — 55 giây, mốc 00:25–01:20.

### English script

> In production, a change in traffic raises an important question: is the model still performing well?<br>
> Distribution monitoring tells us whether recent inputs differ from the reference data. It can work without labels.<br>
> To assess predictive quality, however, we need ground-truth labels, which often arrive later or require human review.<br>
> These signals can disagree. A strong drift alert may accompany good predictions, while missed attacks may produce few alerts.<br>
> This gap motivates our framework: bringing both forms of evidence into model lifecycle decisions.<br>

### Giải thích tiếng Việt

Phân biệt hai câu hỏi. Distribution monitoring kiểm tra dữ liệu đầu vào có thay đổi so với dữ liệu tham chiếu hay không; bước này dùng được khi chưa có nhãn. Quality assessment dùng dự đoán và nhãn đúng để đo mô hình có bỏ sót tấn công hay không. Nhãn có thể đến trễ hoặc cần con người kiểm tra. Hai tín hiệu có thể khác nhau, nên framework cần liên kết cả hai khi hỗ trợ quyết định.

### Gợi ý trình bày

Point to the left column, then the right column. Pause after each question.


## Slide 3 — Scope and Core Contributions

**Thời gian** — 35 giây, mốc 01:20–01:55.

### English script

> Our contributions connect system design with scientific evidence.<br>
> The integrated framework links model versions to their artifacts and monitoring context. A service replay demonstrates the inference-to-monitoring pipeline.<br>
> We evaluate one fixed XGBoost classifier across one hundred and twenty controlled NIDS windows.<br>
> The central finding is that drift share does not consistently rank predictive harm. This supports reviewing distribution alerts alongside labeled quality when making lifecycle decisions.<br>

### Giải thích tiếng Việt

Ba khối tách rõ hệ thống được xây dựng, cách đánh giá và kết quả khoa học. Khối 01 gộp kiến trúc với service replay để minh họa tích hợp inference và monitoring. Khối 02 nêu thực nghiệm 120 window với một classifier cố định, phân biệt thay đổi tỷ lệ attack và thay thế family chưa học. Khối 03 nêu kết quả: drift share không nhất quán trong việc xếp hạng mức suy giảm chất lượng. Đây là bằng chứng hỗ trợ review kết hợp distribution và labeled quality, chưa chứng minh hiệu quả của retraining policy. Kiến trúc hỗ trợ nhiều model; đánh giá chỉ dùng một model và một reference sample.

### Gợi ý trình bày

Follow the cards from left to right: framework, evaluation, then scientific finding. Briefly point to the study scope.


## Slide 4 — Presentation Outline

**Thời gian** — 15 giây, mốc 01:55–02:10.

### English script

> The presentation now follows three parts.<br>
> I will introduce the MLOps framework, examine the NIDS XGBoost case study, and close with a summary of the findings and limitations.<br>

### Giải thích tiếng Việt

Giới thiệu ba phần chính, không đọc toàn bộ tên các slide con. Chuyển từ đóng góp nghiên cứu sang cấu trúc phần trình bày.

### Gợi ý trình bày

Point to each section title briefly, then move to the first section.


## Slide 5 — MLOps Framework

**Thời gian** — 7 giây, mốc 02:10–02:17.

### English script

> Let us begin with the framework and how it connects model operations with monitoring evidence.<br>

### Giải thích tiếng Việt

Chuyển vào phần kiến trúc và các workflow. Không giải thích chi tiết ở trang bìa phần.

### Gợi ý trình bày

Pause briefly, then open Architecture Overview.


## Slide 6 — Architecture Overview

**Thời gian** — 75 giây, mốc 02:17–03:32.

### English script

> Let me first introduce the architecture.<br>
> The Control Plane manages access and model lifecycle state. Its Native Registry connects model versions to their references and monitoring runs, so each report retains its context.<br>
> The Execution Plane runs Kubernetes workloads for building, training, serving, and monitoring. Argo orchestrates the jobs, while prediction clients access the serving API.<br>
> Redpanda and a consumer provide an asynchronous path from inference to production records.<br>
> PostgreSQL holds lifecycle metadata and those records. S3 holds artifacts and reports, and Harbor holds container images.<br>
> Workloads report their results back to the Control Plane. The next slides explain these workflows in more detail.<br>

### Giải thích tiếng Việt

Đây là hình tổng quan theo trách nhiệm. Control Plane quản lý quyền truy cập, tác vụ và metadata. Native Registry là phần quản lý trạng thái, liên kết version với reference và monitoring run. Execution Plane thực thi các workload trên Kubernetes. Argo điều phối tác vụ. Redpanda và consumer chuyển dữ liệu production theo đường bất đồng bộ. PostgreSQL giữ metadata và production records; S3 giữ artifact/reference/report; Harbor giữ container image. Kết quả thực thi quay lại Control Plane dưới dạng trạng thái và tham chiếu báo cáo.

### Gợi ý trình bày

Point left, right, then bottom. Trace the dashed status arrow at the end.


## Slide 7 — Build, Register and Deploy a Model Version

**Thời gian** — 65 giây, mốc 03:32–04:37.

### English script

> Here is how a model becomes a deployed version.<br>
> The user submits a model artifact and its dependencies. An Argo build job reads the input from S3, creates a serving image, and pushes it to Harbor.<br>
> A callback returns the build result to the Control Plane. The Native Registry then records a version with links to its artifacts and image.<br>
> When the user selects that version for deployment, the platform starts a worker Pod and checks its readiness.<br>
> It records the endpoint and health state, keeping the registered version connected to the running service.<br>

### Giải thích tiếng Việt

Giải thích ba giai đoạn theo các cột. Build tạo image phục vụ inference và đẩy lên Harbor. Callback gửi kết quả build về Control Plane. Registry tạo version ID và liên kết các artifact/image tương ứng. Sau đó người dùng chọn version để triển khai. Worker Pod cần khởi chạy và qua kiểm tra readiness; trạng thái metadata đã tồn tại chưa đủ để khẳng định runtime đang sẵn sàng.

### Gợi ý trình bày

Follow the three columns. Use a short pause before registration and before deployment.


## Slide 8 — Prediction Logging and Drift Monitoring

**Thời gian** — 65 giây, mốc 04:37–05:42.

### English script

> Once the service is running, inference and monitoring follow separate paths.<br>
> The gateway forwards a prediction request to the model worker and returns the result to the client.<br>
> After a successful prediction, a background event goes to Redpanda. A consumer processes that event and saves the production record in PostgreSQL.<br>
> For monitoring, an Evidently job compares a window of these records with reference data from S3. The resulting report links back to its monitoring run.<br>
> Because persistence happens asynchronously, a successful prediction response alone does not confirm that the production record reached the database.<br>

### Giải thích tiếng Việt

Đọc hình theo ba hàng. Hàng inference trả dự đoán cho client. Đường bất đồng bộ gửi event tới Redpanda và consumer ghi record vào PostgreSQL. Monitoring job so sánh window production với reference trên S3, tạo report và cập nhật monitoring run. Vì việc lưu record tách khỏi response, prediction thành công không tự chứng minh dữ liệu đã được lưu bền vững. Ngưỡng số record để kích hoạt job khác với ngưỡng kết luận dataset drift.

### Gợi ý trình bày

Trace inference, persistence, then monitoring. Point to both data sources for Evidently.


## Slide 9 — Training Execution Workflow

**Thời gian** — 65 giây, mốc 05:42–06:47.

### English script

> Training follows the path shown here, using the operator version described in the paper.<br>
> The user prepares code, data, and settings in a workspace. The Control Plane records the job, and Argo submits a PyTorchJob to Training Operator version one.<br>
> The scheduler uses an existing node when capacity is available. Otherwise, Karpenter can provision an EC2 node for the workload.<br>
> Inside the training Pod, the runner loads the input, prepares dependencies, and executes the Python script. It then uploads model outputs to S3 and reports the result.<br>
> This describes the configured training path. Evaluating training effectiveness remains outside this study.<br>

### Giải thích tiếng Việt

Giải thích đường training của phiên bản paper, sử dụng Training Operator v1 và PyTorchJob. Runner nằm trong Pod. Scheduler có thể dùng node hiện có; khi cần capacity mới thì Karpenter cấp EC2. Bên trong Pod diễn ra tải Input, chuẩn bị dependencies, chạy script và xuất kết quả. Đây là phạm vi đã cấu hình của hệ thống; paper chưa đánh giá hiệu quả training hoặc chính sách cập nhật mô hình.

### Gợi ý trình bày

Point to the two capacity branches, then the steps inside the Pod.


## Slide 10 — NIDS XGBoost Case Study

**Thời gian** — 7 giây, mốc 06:47–06:54.

### English script

> With the framework in place, let us examine its monitoring behavior through the NIDS case study.<br>

### Giải thích tiếng Việt

Chuyển từ kiến trúc sang thực nghiệm có kiểm soát. Case study đánh giá hành vi monitoring với một classifier cố định.

### Gợi ý trình bày

Introduce the case study and advance to the dataset.


## Slide 11 — Dataset Curation and Fixed-Model Baseline

**Thời gian** — 50 giây, mốc 06:54–07:44.

### English script

> To evaluate monitoring behavior, we use a processed CICIDS twenty seventeen dataset with about two hundred and ten thousand rows and fifty-two numeric features.<br>
> We divide it into four separate pools for training, development, reference, and evaluation, with no exact feature-vector overlap across pools.<br>
> The fixed XGBoost classifier learns from benign traffic and DDoS attacks.<br>
> We hold three other attack families out of training, allowing us to examine its behavior on unfamiliar attacks.<br>

### Giải thích tiếng Việt

Giới thiệu nguồn dữ liệu đã xử lý. Con số chính xác trên slide là 209.844 dòng; khi nói dùng “about two hundred and ten thousand” cho dễ đọc. Bốn pool tách riêng theo tỷ lệ trên hình. Kiểm tra không có vector feature trùng chính xác giữa các pool; điều này chưa bảo đảm các flow/session độc lập. Baseline học từ BENIGN và DDoS, còn PortScan, BruteForce và WebAttacks được giữ ngoài training.

### Gợi ý trình bày

Point to the four pools. The exact row count is visible; the rounded spoken count is intentional.


## Slide 12 — Controlled Shift Scenarios

**Thời gian** — 45 giây, mốc 07:44–08:29.

### English script

> The scenarios separate two types of composition change.<br>
> Our reference contains five thousand rows, with seventy percent benign traffic and thirty percent DDoS.<br>
> S zero preserves that mix. S one changes the attack percentage while keeping the DDoS family.<br>
> S two keeps the total attack percentage fixed, but replaces some attacks with held-out families.<br>
> At twenty-five percent replacement, these unfamiliar attacks make up just seven point five percent of the full window.<br>

### Giải thích tiếng Việt

Reference có 5.000 mẫu với tỷ lệ 70% BENIGN và 30% DDoS. S0 giữ thành phần baseline. S1 thay đổi tỷ lệ attack. S2 giữ tổng attack ở 30% nhưng thay đổi thành phần family. “25% replacement” là 25% trong nhóm attack, tương đương 7,5% toàn window; không phải 25% toàn bộ dữ liệu.

### Gợi ý trình bày

Point to S1, then S2. Emphasize the difference between attack rows and the full window.


## Slide 13 — Monitoring Protocol

**Thời gian** — 45 giây, mốc 08:29–09:14.

### English script

> For each window, we apply a K S test to all fifty-two features, followed by B H correction for multiple testing.<br>
> We calculate the proportion of flagged features and raise an alert when it reaches the chosen threshold. Our principal threshold is zero point three.<br>
> Across one hundred and twenty windows, we test four thresholds and two window sizes: five hundred and one thousand rows.<br>
> Separately, ground-truth labels allow us to assess predictive quality.<br>

### Giải thích tiếng Việt

KS kiểm tra từng feature; BH điều chỉnh các p-value trong mỗi window. Drift share là số feature bị flag chia tổng số feature. Alert được tạo khi drift share đạt threshold; threshold chính là 0,30. Các threshold khác và hai window sizes phục vụ sensitivity analysis. Nhãn dùng cho đánh giá quality ở một nhánh riêng, không đưa vào detector drift.

### Gợi ý trình bày

Read K S and B H as separate letters. Follow the upper monitoring path, then point to quality metrics.


## Slide 14 — Finding 1: Strong Drift with Stable Quality

**Thời gian** — 50 giây, mốc 09:14–10:04.

### English script

> The first finding illustrates why a drift alert needs context.<br>
> In S one, changes in attack prevalence flag roughly seventy-four to ninety-eight percent of features. Every shifted setting triggers alerts in all five windows.<br>
> Yet macro F one remains close to one, because the classifier continues to recognize the DDoS family it learned.<br>
> For an operations team, this alert is useful evidence of a traffic change. Deciding whether to retrain still requires an assessment of predictive quality.<br>

### Giải thích tiếng Việt

S1 thay đổi tỷ lệ attack nên detector phát hiện khác biệt phân phối mạnh, nhưng baseline vẫn nhận diện tốt family DDoS đã học. Macro-F1 tối thiểu khoảng 0,9992. Đây là bằng chứng rằng một distribution alert chưa đủ để kết luận cần retrain. Paper chưa đo chi phí retraining, nên phần nói tập trung vào yêu cầu kiểm tra thêm quality và bối cảnh.

### Gợi ý trình bày

Point to the blue bars, then the quality bars. Pause before the MLOps message.


## Slide 15 — Finding 2: Recall Loss with Few Alerts

**Thời gian** — 50 giây, mốc 10:04–10:54.

### English script

> S two reveals the opposite concern.<br>
> When we replace one quarter of attack rows with unfamiliar attacks, recall falls to about seventy-five percent. In other words, the classifier misses roughly one in four attacks.<br>
> Despite this loss, the monitor raises an alert in only one of five windows.<br>
> The unfamiliar attacks represent just seven point five percent of all rows, illustrating how a change in attack composition can accompany limited alerts.<br>
> This result supports reviewing labeled quality even when the drift monitor remains quiet.<br>

### Giải thích tiếng Việt

Trường hợp S2-r25 có recall trung bình chính xác 75,33%, nhưng chỉ 1/5 window alert. Baseline nhận diện kém các family chưa học, khiến recall tổng giảm khi thành phần attack thay đổi. Held-out attacks chiếm 7,5% cả window. Đây là diễn giải kết quả của mixture; nghiên cứu chưa chứng minh tỷ lệ nhỏ là nguyên nhân duy nhất làm detector ít alert. Quality có nhãn cung cấp bằng chứng review ngay cả khi thiếu alert.

### Gợi ý trình bày

Point to 75.33%, then 1/5. Read the percentage as about seventy-five percent if easier.


## Slide 16 — Drift Share and Predictive Harm

**Thời gian** — 40 giây, mốc 10:54–11:34.

### English script

> Comparing these two settings makes the distinction clear.<br>
> Both flag about ninety-eight percent of features. In S one, macro F one remains close to one. In S two, it falls to about zero point four two, with attack recall near one percent.<br>
> Similar drift shares therefore accompany very different predictive outcomes.<br>
> The framework preserves model-version context so that teams can interpret distribution reports alongside quality evidence.<br>

### Giải thích tiếng Việt

So sánh S1-a85 với S2-r100: drift share gần bằng nhau, khoảng 0,981, nhưng macro-F1 và recall khác rất lớn. Drift share là tỷ lệ feature bị flag, phụ thuộc cấu hình kiểm định; nó không trực tiếp xếp hạng mức suy giảm chất lượng. Liên hệ với framework bằng việc liên kết report và quality đúng model version. S2 phản ánh thay đổi thành phần dữ liệu, không chứng minh mô hình mất kiến thức DDoS theo thời gian.

### Gợi ý trình bày

Compare the two groups from left to right. End on model-version context.


## Slide 17 — Threshold and Window-Size Sensitivity

**Thời gian** — 45 giây, mốc 11:34–12:19.

### English script

> How much do these observations depend on the settings?<br>
> The stable windows produce no alerts in our tested configurations.<br>
> For the small replacement case, lowering the threshold increases alerts from one to two out of five. In another setting, increasing the window size raises that count from one to five.<br>
> Threshold and sample size clearly affect sensitivity, but these examples do not establish a reliable ranking of predictive harm.<br>
> Recording the configuration is therefore essential when interpreting a report.<br>

### Giải thích tiếng Việt

Bảng dùng 30 stable windows cho mỗi kích thước và 5 windows cho mỗi shifted setting. S2-r25, n=1.000: giảm threshold từ 0,30 xuống 0,10 làm alert tăng 1/5 lên 2/5. S2-r50, threshold 0,70: tăng n từ 500 lên 1.000 làm alert tăng 1/5 lên 5/5. Các quan sát này phụ thuộc protocol cụ thể; 0 alert trong stable windows không bảo đảm false-alert rate luôn bằng 0.

### Gợi ý trình bày

Use the two examples on the right. Avoid reading every heatmap cell.


## Slide 18 — Controlled Service Replay

**Thời gian** — 55 giây, mốc 12:19–13:14.

### English script

> We also replay four fixed windows through the deployed service, with one thousand rows in each.<br>
> The live Evidently setup uses different tests from the offline protocol and a threshold of zero point six.<br>
> The main pattern remains: high DDoS prevalence triggers an alert with strong recall, while half replacement reduces recall without an alert.<br>
> The replay also exposes operational interruptions. In the high-DDoS case, forty-two requests fail during worker interruptions. After recovery, all one thousand inputs have recorded predictions, from one thousand and forty-two attempts.<br>
> This provides evidence of pipeline integration, with the observed failures made explicit.<br>

### Giải thích tiếng Việt

Service replay kiểm tra tích hợp bằng 4 window đã chốt, mỗi window 1.000 mẫu. Evidently service dùng cấu hình khác KS/BH và threshold dataset là 0,60. S1-a85 alert với recall 1,0000; S2-r50 không alert dù recall chỉ 0,5067. Paper ghi 42 HTTP 502/503 failures ở S1 và final coverage đạt 1.000 record từ 1.042 attempts. Điều này mô tả coverage cuối cùng, chưa thiết lập bảo đảm retry idempotency hoặc exactly-once. Evidently 0.4.15 là cấu hình được pin trong source, chưa có runtime inventory lưu trữ đầy đủ.

### Gợi ý trình bày

Point to the threshold line and the S2-r50 table row. Pause before explaining recovery.



### Additional production timing

The median inference p95 was 355 milliseconds. 2 of three windows produced reports, with median availability of 44.9 seconds. A client transport error left one window below the sample threshold.

Bổ sung thời gian vận hành trên cụm triển khai lại. Đo ba lượt S0, mỗi lượt 1.000 request, tải mục tiêu 5 request/giây. p95 đo từ máy khách qua HTTPS public. Thời gian report tính từ trước request cuối đến khi đọc được JSON và HTML, gồm polling hai giây. Đợt đo tháng 11 có provenance riêng với replay tháng 9. Đoạn nói bổ sung khoảng 20 giây. Thời gian report chỉ tổng hợp trên 2/3 cửa sổ hoàn tất. Một ReadError khiến cửa sổ đầu chỉ có 999 record và không kích hoạt report. p95 dùng các response thành công, lỗi client được công bố riêng trong báo cáo. Bằng chứng đo mới nằm trong research/experiments/production_timing/results/run_20261115/.

## Slide 19 — Summary

**Thời gian** — 6 giây, mốc 13:14–13:20.

### English script

> Finally, I will summarize the main findings, then clarify the limits of our evaluation.<br>

### Giải thích tiếng Việt

Báo hiệu phần tổng kết, gồm giới hạn khoa học và kết luận.

### Gợi ý trình bày

Introduce the conclusion first, followed by its limitations.


## Slide 20 — Conclusions

**Thời gian** — 40 giây, mốc 13:20–14:00.

### English script

> The results show why distribution alerts alone are insufficient for model lifecycle decisions.<br>
> In S one, all five windows trigger alerts while macro F one remains close to one.<br>
> At twenty-five percent replacement in S two, recall falls to about seventy-five percent, but only one of five windows triggers an alert.<br>
> These findings support reviewing drift and predictive quality together, with the deployed model version as context.<br>
> Let me close by clarifying the boundaries of this evidence.<br>

### Giải thích tiếng Việt

Kết luận dựa trên hai kết quả đối chiếu: S1 có alert mạnh nhưng quality ổn định; S2-r25 có recall giảm còn 75,33% nhưng chỉ 1/5 cửa sổ alert. Các số quality là trung bình ở n=1.000 với năm principal seeds. Hai bằng chứng cho thấy không thể chỉ dùng alert để quyết định lifecycle. Hàm ý là review cả distribution và labeled quality theo đúng version đã triển khai, chưa chứng minh hiệu quả của policy retraining. Câu cuối chuyển sang Scientific Limitations.

### Gợi ý trình bày

Read the main conclusion, compare the two evidence blocks, then point to the MLOps implication. Transition to the limitations.


## Slide 21 — Scientific Limitations

**Thời gian** — 30 giây, mốc 14:00–14:30.

### English script

> These findings apply within a defined scope.<br>
> We use a processed dataset without the time information needed for a temporal study, and evaluate one fixed classifier with one reference sample.<br>
> The service replay demonstrates integration. Scalability, tenant isolation, and the effectiveness of update policies still require separate evaluation.<br>
> Thank you. I would be happy to take your questions.<br>

### Giải thích tiếng Việt

Phạm vi gồm dữ liệu đã xử lý và thiếu thông tin thời gian, một classifier và một reference cố định. Replay chứng minh tích hợp trong thử nghiệm, chưa đánh giá scalability, isolation hay hiệu quả update policy. Chốt giới hạn rồi chuyển sang trang Questions.

### Gợi ý trình bày

Briefly cover the three limitation groups, then move to Questions.


## Slide 22 — Thank You and Questions

**Thời gian** — 5 giây, mốc 14:30–14:35.

### English script

> Thank you for your attention.<br>
> I would be happy to take your questions.<br>

### Giải thích tiếng Việt

Cảm ơn khán giả và mời đặt câu hỏi. Giữ trang này trên màn hình trong phần phản biện 5 phút.

### Gợi ý trình bày

Pause and wait for questions.


## Slide 23 — References

**Thời gian** — Trang backup, dùng khi được hỏi. Phần giới thiệu tham khảo khoảng 15 giây trong Q&A.

### English script

> These references provide the background for our framework and evaluation, including MLOps architecture, dataset shift, the intrusion dataset, XGBoost, and statistical testing.<br>
> I can refer to the relevant study if you would like more detail.<br>

### Giải thích tiếng Việt

Trang backup dùng khi khán giả hỏi về tài liệu liên quan. Nội dung này không được tính vào 14 phút 35 giây phần nói chính. Có thể trả lời nguồn theo từng nhóm chủ đề thay vì đọc toàn bộ tên bài.

### Gợi ý trình bày

Backup only. Allow about 15 seconds if you need to introduce the references during Q&A.


## Cách đọc một số thuật ngữ và số liệu

| Viết trên slide | Cách đọc bằng tiếng Anh | Ý nghĩa |
|---|---|---|
| MLOps | em el ops | Vận hành vòng đời mô hình ML |
| API | ay pee eye | Giao diện gọi dịch vụ |
| KS / BH | kay ess / bee aitch | Kiểm định KS / điều chỉnh BH |
| S0 / S1 / S2 | ess zero / ess one / ess two | Tên các nhóm scenario |
| S3 | ess three | Object storage |
| EC2 | ee see two | Tài nguyên máy EC2 |
| GPU | gee pee you | Thiết bị tăng tốc GPU |
| XGBoost | ex gee boost | Tên thư viện/mô hình |
| F1 | eff one | Chỉ số F1 |
| 0.30 | zero point three | Threshold chính của offline study |
| 0.60 | zero point six | Threshold của service replay |
| 1/5 | one out of five | Một trong năm cửa sổ |
| 75.33% | seventy-five point three three percent | Trong lời nói có thể dùng about seventy-five percent |
| 1,000 | one thousand | Một nghìn |
| 1,042 | one thousand and forty-two | Số attempts ở S1 service replay |


## Một vài câu dùng trong phần phản biện

- **Could you please repeat the question?** — Anh/chị có thể nhắc lại câu hỏi không?

- **Could you please speak a little more slowly?** — Anh/chị có thể nói chậm hơn một chút không?

- **Let me explain this using the diagram.** — Tôi xin giải thích bằng sơ đồ.

- **We have not evaluated that yet. It is part of our future work.** — Chúng tôi chưa đánh giá phần đó. Đây là hướng nghiên cứu tiếp theo. Chỉ dùng câu này khi đúng với phạm vi câu hỏi.


Các số được làm tròn trong lời nói để dễ đọc; số chính xác tiếp tục nằm trên slide. Phần giải thích tiếng Việt giữ các điều kiện và giới hạn cần hiểu khi trả lời câu hỏi.
