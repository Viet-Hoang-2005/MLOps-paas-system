# CSoNet 2026 — Nội dung thuyết trình

## Cách sử dụng

Đọc **English script** khi thuyết trình. Lời nói dùng tiếng Anh tự nhiên, dễ đọc; phần tiếng Việt giải thích nội dung và giới hạn bằng chứng. Speaker Notes trong PowerPoint có cùng nội dung, kèm nguồn và gợi ý chuyển ý.

Câu chuyện chung: **Framework liên kết model version với bằng chứng monitoring; NIDS kiểm tra cách diễn giải bằng chứng khi review model.**

Thời gian dự kiến **14 phút 35 giây**, dành **25 giây dự phòng** trong 15 phút trình bày. Q&A riêng **5 phút**. Thời gian là mốc tập dượt, cần kiểm tra bằng đọc thử thực tế.

## Thời gian từng slide

| Slide | Nội dung | Thời lượng | Mốc trong bài |
|---|---|---|---|
| 1 | Title | 25 giây | 00:00–00:25 |
| 2 | Distribution Alerts and Predictive Quality | 55 giây | 00:25–01:20 |
| 3 | Scope and Core Contributions | 35 giây | 01:20–01:55 |
| 4 | Presentation Outline | 15 giây | 01:55–02:10 |
| 5 | MLOps Framework | 7 giây | 02:10–02:17 |
| 6 | Architecture Overview | 65 giây | 02:17–03:22 |
| 7 | Build, Register and Deploy a Model Version | 65 giây | 03:22–04:27 |
| 8 | Prediction Logging and Drift Monitoring | 65 giây | 04:27–05:32 |
| 9 | Training Execution Workflow | 40 giây | 05:32–06:12 |
| 10 | NIDS XGBoost Case Study | 7 giây | 06:12–06:19 |
| 11 | NIDS Evaluation within the MLOps Framework | 40 giây | 06:19–06:59 |
| 12 | Dataset Curation and Fixed-Model Baseline | 50 giây | 06:59–07:49 |
| 13 | Controlled Shift Scenarios | 45 giây | 07:49–08:34 |
| 14 | Monitoring Protocol | 45 giây | 08:34–09:19 |
| 15 | Finding 1: Strong Drift with Stable Quality | 50 giây | 09:19–10:09 |
| 16 | Finding 2: Recall Loss with Few Alerts | 50 giây | 10:09–10:59 |
| 17 | Drift Share and Predictive Harm | 40 giây | 10:59–11:39 |
| 18 | Threshold and Window-Size Sensitivity | 40 giây | 11:39–12:19 |
| 19 | NIDS Service Replay on the MLOps Framework | 55 giây | 12:19–13:14 |
| 20 | Summary | 6 giây | 13:14–13:20 |
| 21 | Conclusions | 40 giây | 13:20–14:00 |
| 22 | Scientific Limitations | 30 giây | 14:00–14:30 |
| 23 | Thank You and Questions | 5 giây | 14:30–14:35 |
| 24 | References | Backup / khoảng 15 giây | Trong Q&A |
| 25 | Model Configuration, Build and Deployment | Backup / khoảng 40 giây | Trong Q&A |
| 26 | Prediction Logging and Drift Monitoring | Backup / khoảng 45 giây | Trong Q&A |
| 27 | Training Workspace and Model Version Artifacts | Backup / khoảng 45 giây | Trong Q&A |


## Slide 1 — Title

**Thời gian** — 25 giây, mốc 00:00–00:25.

### English script

> Good morning, everyone. My name is Hoang Tran-Nguyen-Viet , and I am from the University of Information Technology in Vietnam.<br>
> Today, I will present our drift-aware MLOps framework for multi-model serving, using network intrusion detection as a case study.<br>

### Giải thích tiếng Việt

Chào khán giả, giới thiệu tên và đơn vị. Bài trình bày tập trung vào khung MLOps và cách liên kết vận hành mô hình với bằng chứng giám sát. Phát hiện tấn công mạng là bài toán dùng để đánh giá hệ thống.

### Gợi ý trình bày

Pause after your name and the presentation topic. Point to the paper title.

---

## Slide 2 — Distribution Alerts and Predictive Quality

**Thời gian** — 55 giây, mốc 00:25–01:20.

### English script

> Production teams face two questions when traffic changes. Has the input distribution changed? And are attacks being missed?<br>
> Distribution monitoring compares current features with a reference, without needing labels. Assessing predictive quality requires ground truth, which may arrive later.<br>
> Our MLOps question is therefore: what evidence should guide a model update?<br>
> The framework connects monitoring reports with model-version context. The NIDS study examines why operators should also consider labeled quality before deciding what to review.<br>

### Giải thích tiếng Việt

Hai câu hỏi dẫn tới cùng một quyết định MLOps: khi nào cần xem xét cập nhật model. Distribution monitoring không cần nhãn; đánh giá quality cần ground truth. Framework liên kết version/reference/report; kết quả NIDS giải thích vì sao cần xem xét cả hai tín hiệu. Không khẳng định nền tảng đã tự động thu thập nhãn hoặc thực thi policy review.

### Gợi ý trình bày

Point to the two questions, then the model-update question. Transition to the contributions.

---

## Slide 3 — Scope and Core Contributions

**Thời gian** — 35 giây, mốc 01:20–01:55.

### English script

> The contributions follow that question.<br>
> First, the framework links model versions with their artifacts, references and monitoring reports. A service replay demonstrates the integration path.<br>
> Second, we compare distribution alerts with labeled quality across one hundred and twenty controlled NIDS windows.<br>
> Third, the results motivate model review using both signals and the deployed version as context. The reviewed update policy remains a design implication, rather than an evaluated policy.<br>

### Giải thích tiếng Việt

Ba khối liên kết: framework tổ chức bằng chứng; evaluation kiểm tra ý nghĩa của bằng chứng; kết quả hỗ trợ thiết kế review. Đóng góp được đánh giá chính là nghiên cứu có kiểm soát và hàm ý lifecycle, không phải phát minh mới về registry. Policy review/update chưa được đánh giá.

### Gợi ý trình bày

Follow framework, evaluation and design implication. Present them as connected contributions.

---

## Slide 4 — Presentation Outline

**Thời gian** — 15 giây, mốc 01:55–02:10.

### English script

> The three parts follow the same question.<br>
> How the framework connects monitoring evidence to model versions. Next, what the NIDS case study reveals about that evidence. Finally, the implications and limitations.<br>

### Giải thích tiếng Việt

Mục lục thể hiện quan hệ: phần một tổ chức bằng chứng, phần hai kiểm tra ý nghĩa, phần ba rút ra hàm ý. Không giới thiệu hai đề tài độc lập.

### Gợi ý trình bày

Point to the three descriptions without reading each title twice.

---

## Slide 5 — MLOps Framework

**Thời gian** — 7 giây, mốc 02:10–02:17.

### English script

> Let us begin with the framework and how it manages the lifecycle of multiple models.<br>

### Giải thích tiếng Việt

Giới thiệu tổng quan khung MLOps phục vụ nhiều mô hình. Phần này giải thích kiến trúc và các workflow chung; phần sau mới đi vào bài toán ứng dụng cụ thể.

### Gợi ý trình bày

Introduce the multi-model framework, then advance to the architecture.

---

## Slide 6 — Architecture Overview

**Thời gian** — 65 giây, mốc 02:17–03:22.

### English script

> The framework organizes multiple model projects and their versions through a shared Control Plane.<br>
> Users manage these projects through the dashboard. The Control Plane handles access and lifecycle state, while the Native Registry links each version to its artifacts, reference data and monitoring runs.<br>
> The Execution Plane runs build, training, serving and monitoring workloads on Kubernetes. Argo corchestrates the jobs, and the gateway routes prediction requests to the selected model version.<br>
> PostgreSQL stores lifecycle metadata and production records. S3 holds artifacts and reports, while Harbor stores serving images.<br>
> This structure gives different models a common operational workflow while retaining their individual version context.<br>

### Giải thích tiếng Việt

Giải thích kiến trúc theo trách nhiệm và phạm vi đa mô hình: nhiều Model Project, mỗi project có các version; Control Plane quản lý truy cập và lifecycle, Native Registry giữ các liên kết. Execution Plane thực thi workload trên Kubernetes, Argo điều phối job và gateway định tuyến theo model/version. PostgreSQL lưu metadata/production records, S3 lưu artifact/reference/report, Harbor lưu image. Đây là mô tả kiến trúc, không khẳng định đã benchmark khả năng mở rộng nhiều model hoặc chứng nhận cách ly tenant. Liên kết version không tự bảo đảm reference bytes/window membership bất biến.

### Gợi ý trình bày

Introduce the Control Plane, then the Execution Plane and shared storage. End on how each model retains its version context.

---

## Slide 7 — Build, Register and Deploy a Model Version

**Thời gian** — 65 giây, mốc 03:22–04:27.

### English script

> This workflow turns a model artifact into a version that can serve predictions.<br>
> The user supplies the artifact and its dependencies. An Argo build job reads the inputs from S3, prepares a serving image and pushes it to Harbor. A callback returns the build result to the Control Plane.<br>
> The Native Registry records a version linked to the image and its artifacts. The user can then select that version for deployment.<br>
> The platform starts a worker Pod, checks initial readiness and records the endpoint.<br>
> The same workflow applies across model projects, with each version retaining its own artifacts, image identity and deployment context.<br>

### Giải thích tiếng Việt

Trình bày luồng chung build image, register version và deploy version theo sơ đồ. Artifact/dependencies là đầu vào; callback trả kết quả build; registry lưu version cùng liên kết artifact/image. Khi người dùng deploy, worker Pod khởi chạy và được kiểm tra readiness ban đầu, sau đó quản lý endpoint/health. Các model project dùng chung quy trình nhưng vẫn có định danh và artifact riêng. Không diễn giải mỗi model bắt buộc có một EC2 riêng hoặc được bảo đảm chạy đồng thời.

### Gợi ý trình bày

Follow build, registration and deployment. Point to the version links before moving to prediction logging.

---

## Slide 8 — Prediction Logging and Drift Monitoring

**Thời gian** — 65 giây, mốc 04:27–05:32.

### English script

> After deployment, inference and monitoring follow separate paths.<br>
> The gateway forwards each prediction request to the selected model worker and returns the response to the client. After a successful prediction, a background event goes to Redpanda. A consumer processes the event and stores the production record in PostgreSQL.<br>
> For monitoring, an Evidently job compares a window of production features with reference data from S3. The report links back to its monitoring run and model version.<br>
> This keeps distribution evidence associated with the model that produced the predictions. Because persistence is asynchronous, a prediction response alone does not confirm that the record has reached the database.<br>

### Giải thích tiếng Việt

Giải thích ba đường chung: inference trả response, Redpanda/consumer ghi dữ liệu bất đồng bộ, Evidently so sánh current window với reference. Records và report giữ bối cảnh model/version, phục vụ theo dõi từng deployment trong kiến trúc đa mô hình. Monitoring ở đây cung cấp distribution evidence; không mô tả pipeline tự thu thập ground-truth labels, tự đánh giá accuracy hoặc tự retrain. Prediction thành công không bảo đảm DB đã persist, và latest records chưa chứng nhận frozen window membership.

### Gợi ý trình bày

Trace inference, asynchronous persistence and monitoring in order. Point to the production and reference inputs to Evidently.

---

## Slide 9 — Training Execution Workflow

**Thời gian** — 40 giây, mốc 05:32–06:12.

### English script

> The training workflow lets users prepare model artifacts within the platform.<br>
> They provide code, data and resource settings in a workspace. The Control Plane records the job, and Argo submits a PyTorchJob through Training Operator version one.<br>
> The scheduler uses available capacity, while Karpenter can provision an EC2 node when needed. Inside the Pod, the runner prepares dependencies and executes the Python script.<br>
> The outputs return to S3 and can enter the build, registration and deployment workflow.<br>

### Giải thích tiếng Việt

Trình bày training như workflow chung để tạo artifact. Giữ phiên bản kiến trúc paper là Training Operator v1/PyTorchJob; không đổi thành Trainer v2 của tiến độ triển khai hiện tại. Runner thực thi Python user code, không đồng nghĩa mọi model phải là framework PyTorch. Scheduler dùng node phù hợp hiện có hoặc Karpenter bổ sung capacity nếu điều kiện/quota cho phép; không phải mỗi job luôn được tạo EC2 riêng. Outputs là đầu vào cho các bước build/register/deploy tiếp theo, không mô tả tự động promote sau training.

### Gợi ý trình bày

Follow workspace submission, Pod execution and output publication. End on the connection back to the build workflow.



## Slide 10 — NIDS XGBoost Case Study

**Thời gian** — 7 giây, mốc 06:12–06:19.

### English script

> We now use NIDS to examine the monitoring evidence that should inform model review.<br>

### Giải thích tiếng Việt

Chuyển sang NIDS như một phép khảo sát câu hỏi MLOps vừa đặt ra. Slide tiếp theo phân biệt hai nhánh bằng chứng.

### Gợi ý trình bày

Advance to the bridge before discussing the dataset.

---

## Slide 11 — NIDS Evaluation within the MLOps Framework

**Thời gian** — 40 giây, mốc 06:19–06:59.

### English script

> The case study connects to the framework through two kinds of evidence.<br>
> The offline study uses one fixed classifier and reference across one hundred and twenty controlled windows. We compare distribution tests with labeled predictive quality to examine what each signal reveals.<br>
> Separately, four windows pass through the deployed NIDS service, asynchronous logging and Evidently monitoring. This checks the integration path.<br>
> The detectors differ, and the proposed review policy remains unevaluated. Let us first look at the data behind the controlled study.<br>

### Giải thích tiếng Việt

Hàng trên: 120 windows chạy offline, dùng KS/BH và nhãn để so sánh distribution với quality. Hàng dưới: 4 service replay windows kiểm tra inference/logging/Evidently trên nền tảng. Hai nhóm bổ sung bằng chứng nhưng không tương đương detector/protocol và không có nghĩa 120 windows chạy production. Review dùng nét đứt vì là đề xuất chưa đo hiệu quả.

### Gợi ý trình bày

Trace the upper evidence path, then the lower integration path. Keep the two scopes distinct.

---

## Slide 12 — Dataset Curation and Fixed-Model Baseline

**Thời gian** — 50 giây, mốc 06:59–07:49.

### English script

> We begin with the data used to generate the monitoring evidence.<br>
> The processed CICIDS twenty seventeen derivative contains about two hundred and ten thousand rows and fifty-two numeric features.<br>
> We separate training, development, reference and evaluation pools, with no exact feature-vector overlap across them.<br>
> One fixed XGBoost classifier learns benign traffic and DDoS. Three other attack families remain unseen during fitting.<br>
> This gives us a controlled way to compare distribution alerts with predictive quality as traffic composition changes.<br>

### Giải thích tiếng Việt

Dataset phục vụ khảo sát monitoring trong bối cảnh NIDS. Giữ 209.844 retained rows, 52 features và tỷ lệ pools như hình. Zero exact-vector overlap không bảo đảm session independence hoặc upstream lineage. Fixed model/reference giúp giảm yếu tố gây nhiễu; chưa chứng minh generalization cho mọi model.

### Gợi ý trình bày

Connect the four pools to the reference and current-window inputs on the bridge.

---

## Slide 13 — Controlled Shift Scenarios

**Thời gian** — 45 giây, mốc 07:49–08:34.

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

---

## Slide 14 — Monitoring Protocol

**Thời gian** — 45 giây, mốc 08:34–09:19.

### English script

> The offline protocol separates two evidence paths.<br>
> K S tests compare all fifty-two features with the reference, followed by B H correction. The proportion of flagged features produces a distribution alert at the chosen threshold, with zero point three as the principal setting.<br>
> Separately, predictions and known labels produce quality metrics.<br>
> We compare these signals across one hundred and twenty windows, two sizes and four thresholds. This is the controlled study, rather than the live Evidently detector.<br>

### Giải thích tiếng Việt

Hai nhánh trên sơ đồ tương ứng cầu nối: distribution không dùng nhãn; quality dùng held-out labels. KS/BH của offline khác detector Evidently service. 120 windows là tổng across sizes; threshold chính 0,30 và các threshold còn lại đã định trước.

### Gợi ý trình bày

Point to the distribution path, then the labeled-quality path. Introduce the two findings.

---

## Slide 15 — Finding 1: Strong Drift with Stable Quality

**Thời gian** — 50 giây, mốc 09:19–10:09.

### English script

> The first finding illustrates why a drift alert needs context.<br>
> In S one, changes in attack prevalence flag roughly seventy-four to ninety-eight percent of features. Every shifted setting triggers alerts in all five windows.<br>
> Yet macro F one remains close to one, because the classifier continues to recognize the DDoS family it learned.<br>
> For an operations team, this alert is useful evidence of a traffic change. Deciding whether to retrain still requires an assessment of predictive quality.<br>

### Giải thích tiếng Việt

S1 thay đổi tỷ lệ attack nên detector phát hiện khác biệt phân phối mạnh, nhưng baseline vẫn nhận diện tốt family DDoS đã học. Macro-F1 tối thiểu khoảng 0,9992. Đây là bằng chứng rằng một distribution alert chưa đủ để kết luận cần retrain. Paper chưa đo chi phí retraining, nên phần nói tập trung vào yêu cầu kiểm tra thêm quality và bối cảnh.

### Gợi ý trình bày

Point to the blue bars, then the quality bars. Pause before the MLOps message.

---

## Slide 16 — Finding 2: Recall Loss with Few Alerts

**Thời gian** — 50 giây, mốc 10:09–10:59.

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

---

## Slide 17 — Drift Share and Predictive Harm

**Thời gian** — 40 giây, mốc 10:59–11:39.

### English script

> Comparing these two settings makes the distinction clear.<br>
> Both flag about ninety-eight percent of features. In S one, macro F one remains close to one. In S two, it falls to about zero point four two, with attack recall near one percent.<br>
> Similar drift shares therefore accompany very different predictive outcomes.<br>
> The framework preserves model-version context so that teams can interpret distribution reports alongside quality evidence.<br>

### Giải thích tiếng Việt

So sánh S1-a85 với S2-r100: drift share gần bằng nhau, khoảng 0,981, nhưng macro-F1 và recall khác rất lớn. Drift share là tỷ lệ feature bị flag, phụ thuộc cấu hình kiểm định; nó không trực tiếp xếp hạng mức suy giảm chất lượng. Liên hệ với framework bằng việc liên kết report và quality đúng model version. S2 phản ánh thay đổi thành phần dữ liệu, không chứng minh mô hình mất kiến thức DDoS theo thời gian.

### Gợi ý trình bày

Compare the groups, then point to the model-review implication.

### Nguồn và phạm vi

Controlled study: run_20260926, scenario_summary.csv, threshold_summary.csv and split/model manifests. Means and sample SD use the stated seeds. S0 alert counts use 30 windows per size. Offline KS/BH; not the service detector.


## Slide 18 — Threshold and Window-Size Sensitivity

**Thời gian** — 40 giây, mốc 11:39–12:19.

### English script

> Monitoring settings also matter.<br>
> The stable windows produce no alerts in the tested configurations. For the small replacement case, lowering the threshold raises alerts from one to two out of five. In another setting, a larger window raises that count from one to five.<br>
> These choices affect alert frequency, but cannot establish predictive harm. Model review must interpret the report together with its configuration and labeled quality.<br>

### Giải thích tiếng Việt

Nêu hai ví dụ đang có trên heatmap. 0/30 là finite observation, không phải bảo đảm false-alert rate bằng không. Threshold/window size ảnh hưởng detector; không thay thế đánh giá chất lượng. Các kết quả là offline KS/BH, tiếp theo replay dùng detector khác.

### Gợi ý trình bày

Use the two right-hand examples. Transition from signal interpretation to platform integration.

---

## Slide 19 — NIDS Service Replay on the MLOps Framework

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

---

## Slide 20 — Summary

**Thời gian** — 6 giây, mốc 13:14–13:20.

### English script

> We can now connect the NIDS findings to the framework's model lifecycle design.<br>

### Giải thích tiếng Việt

Phần tổng kết nối kết quả thực nghiệm với cách tổ chức bằng chứng trong framework.

### Gợi ý trình bày

Advance to the conclusions.

---

## Slide 21 — Conclusions

**Thời gian** — 40 giây, mốc 13:20–14:00.

### English script

> The NIDS results show why model review needs both distribution evidence and labeled quality.<br>
> S one produces strong alerts with stable quality. In S two, recall falls to about seventy-five percent while only one of five windows triggers an alert.<br>
> The framework links versions, references and monitoring reports, giving operators context for this evidence.<br>
> Together, these contributions motivate reviewed lifecycle decisions. Whether that review leads to better model updates still requires a separate evaluation.<br>

### Giải thích tiếng Việt

Kết luận kết nối hai phần: framework tổ chức bối cảnh version/reference/report; NIDS chứng minh các tín hiệu có thể bất đồng. Điều này motivate reviewed decisions, chưa chứng minh policy giúp cải thiện update. Giữ ví dụ S1 và S2-r25 trên slide.

### Gợi ý trình bày

Compare the two evidence blocks, connect them to the framework, and move to the limitations.

---

## Slide 22 — Scientific Limitations

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

---

## Slide 23 — Thank You and Questions

**Thời gian** — 5 giây, mốc 14:30–14:35.

### English script

> Thank you for your attention.<br>
> I would be happy to take your questions.<br>

### Giải thích tiếng Việt

Cảm ơn khán giả và mời đặt câu hỏi. Giữ trang này trên màn hình trong phần phản biện 5 phút.

### Gợi ý trình bày

Pause and wait for questions.

---

## Slide 24 — References

**Thời gian** — Trang backup, khoảng 15 giây khi được hỏi; không tính vào phần trình bày chính.

### English script

> These references provide the background for our framework and evaluation, including MLOps architecture, dataset shift, the intrusion dataset, XGBoost, and statistical testing.<br>
> I can refer to the relevant study if you would like more detail.<br>

### Giải thích tiếng Việt

Trang backup dùng khi khán giả hỏi về tài liệu liên quan. Nội dung này không được tính vào 14 phút 35 giây phần nói chính. Có thể trả lời nguồn theo từng nhóm chủ đề thay vì đọc toàn bộ tên bài.

### Gợi ý trình bày

Backup only. Allow about 15 seconds if you need to introduce the references during Q&A.

---

## Slide 25 — Model Configuration, Build and Deployment

**Thời gian** — Trang backup, khoảng 40 giây khi được hỏi; không tính vào phần trình bày chính.

### English script

> These screenshots illustrate how a user prepares and deploys a model through the platform.<br>
> The configuration screen captures the model framework and API access settings.<br>
> After the image is built, the user can register a model version and deploy it.<br>
> The overview then displays the deployment status and resource usage.<br>
> The main point is that these steps are connected through the platform, allowing the user to follow the model from configuration to a running service.<br>
> These are prototype interface examples.<br>
> The displayed resource values are snapshots, rather than controlled production benchmark results.<br>

### Giải thích tiếng Việt

Giải thích luồng cấu hình framework và quyền truy cập API, build image, đăng ký version rồi deploy. Các ảnh được ghép để minh họa chức năng, không theo thứ tự thao tác trên slide. Ảnh có endpoint localhost và log Docker, vì vậy không dùng chúng làm bằng chứng thực nghiệm K3s production. Các giá trị CPU, RAM và requests/second chỉ là số tức thời trong giao diện.

### Gợi ý trình bày

Point to configuration, build, deployment, and overview in that order. Use this slide to explain the interface, not to make performance claims.

---

## Slide 26 — Prediction Logging and Drift Monitoring

**Thời gian** — Trang backup, khoảng 45 giây khi được hỏi; không tính vào phần trình bày chính.

### English script

> This slide illustrates the path from prediction testing to drift monitoring.<br>
> The prediction interface displays responses and test progress, while the production-data preview shows records available for monitoring.<br>
> The user can configure a record-count trigger or request a drift check manually, then inspect the report and individual feature results.<br>
> The record-count trigger determines when a check starts.<br>
> The drift-share threshold determines whether the report raises an alert.<br>
> These screenshots show an illustrative run with 202 samples and 53 displayed columns.<br>
> They are separate from the paper's controlled evaluation.<br>
> The displayed accuracy and drift score should therefore not be interpreted as research results.<br>

### Giải thích tiếng Việt

Minh họa kiểm thử prediction, dữ liệu production đã ghi và báo cáo drift. Phân biệt ngưỡng số bản ghi dùng để kích hoạt job với ngưỡng drift share dùng để kết luận cảnh báo. Ảnh report có 202 mẫu và 53 cột hiển thị, khác protocol nghiên cứu dùng 1.000 mẫu/cửa sổ và 52 feature. Không dùng accuracy 46% của lần test đang chạy, drift score hoặc “drift detection rate” trong ảnh như metric nghiên cứu. Các panel không chứng minh monitor đã tự kích hoạt khi đủ ngưỡng; giao diện cũng cho phép chạy thủ công.

### Gợi ý trình bày

Follow prediction testing, production records, monitoring controls, and the report. If asked about the numbers, distinguish these interface examples from the frozen experimental results.

---

## Slide 27 — Training Workspace and Model Version Artifacts

**Thời gian** — Trang backup, khoảng 45 giây khi được hỏi; không tính vào phần trình bày chính.

### English script

> These screenshots illustrate the training interface and its connection to model management.<br>
> Users prepare code, data, dependencies, and resource settings in a workspace.<br>
> During execution, they can inspect training logs and resource usage.<br>
> After a successful run, they can select the job and associate its outputs with a model project.<br>
> The version interface then provides access to the associated artifacts.<br>
> This demonstrates the user workflow, rather than a measured retraining policy.<br>
> The training example is separate from the frozen classifier used in our experiments.<br>
> The GTX 1650 shown here belongs to the demonstration environment, rather than the production cluster.<br>

### Giải thích tiếng Việt

Giới thiệu workspace, cấu hình tài nguyên, theo dõi log và liên kết output của job đã thành công với Model Project. Sau đó giải thích giao diện version lưu các artifact liên quan. Không suy ra các ảnh thuộc cùng một lần chạy, không khẳng định ảnh log Running chứng minh job đó đã hoàn thành, và không nói việc gán Project tự động Build/Deploy. Ví dụ training này không thay model frozen trong paper; GTX 1650 là máy demo, không phải GPU production.

### Gợi ý trình bày

Point to the workspace, live logs, completed-job selection, and version artifacts. Explain the available workflow without claiming that automated retraining was evaluated.

---

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