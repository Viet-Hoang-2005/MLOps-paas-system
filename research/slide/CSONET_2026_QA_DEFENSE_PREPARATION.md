# CSoNet 2026 — Câu hỏi phản biện

Paper: **A Drift-Aware MLOps Framework for Multi-Model Serving**.

Tài liệu tập luyện cho **5 phút Q&A**, theo deck 27 slide hiện tại. Câu hỏi và câu trả lời nói trực tiếp dùng tiếng Anh; phần tiếng Việt giúp hiểu lý do và giới hạn bằng chứng. Các câu trả lời là gợi ý, không phải trích dẫn nguyên văn paper.

## 1. Cách chuẩn bị

- Ưu tiên học Q1–Q5, Q10, Q13, Q18, Q23 và Q28 trước. Đây là nhóm có khả năng chạm vào đóng góp và giới hạn nghiên cứu.
- Mỗi câu trả lời nên bắt đầu bằng một ý trực tiếp, sau đó đưa một bằng chứng và một giới hạn nếu cần. Mục tiêu khoảng **20–40 giây**, không đọc cả phần giải thích tiếng Việt.
- Khi câu hỏi có nhiều ý, trả lời ý chính trước và xin phép giải thích tiếp nếu người hỏi muốn đi sâu.
- Phân biệt ba mức: **chức năng của prototype**, **kết quả đã đo trong paper**, **chính sách được đề xuất hoặc công việc tương lai**.
- Phần Framework nói về kiến trúc đa mô hình. Chỉ nối sang NIDS khi cần giải thích phạm vi đánh giá; không biến mọi câu hỏi kiến trúc thành câu trả lời về classifier.

### Ba câu cần nhớ

> The framework links model versions with artifacts, reference data and monitoring reports.

> The controlled study shows that distribution alerts and labeled predictive quality can disagree.

> The service replay provides integration evidence. The effectiveness of the proposed update policy remains unevaluated.

## 2. Đóng góp và mối liên hệ giữa framework với case study

### Q1. What is the main scientific contribution of this work? ⭐

**Trả lời tiếng Anh:**

> Our main evaluated contribution is a controlled study of disagreement between distribution alerts and predictive quality. We quantify this across 120 NIDS windows and use the findings to motivate model review with separate evidence linked to the deployed version. The framework makes this lifecycle design concrete, while the service replay provides integration evidence.

**Giải thích tiếng Việt:** Đặt trọng tâm vào nghiên cứu có kiểm soát và hàm ý thiết kế lifecycle. Kiến trúc là prototype hiện thực hóa ý tưởng, không phải một detector hoặc registry technology mới.

**Slide hỗ trợ:** 3, 11, 15–17, 21.

### Q2. How does the NIDS case study relate to the MLOps framework? ⭐

**Trả lời tiếng Anh:**

> The framework organizes model versions and their monitoring reports. The NIDS study examines how operators should interpret that evidence before reviewing a model. The offline experiment studies the monitoring signals, and the service replay exercises the platform's inference-to-monitoring path. These are complementary forms of evidence with different scopes.

**Giải thích tiếng Việt:** Dùng slide cầu nối để chỉ rõ hai nhánh. Không nói toàn bộ 120 windows đã chạy qua hệ thống production hoặc toàn bộ vòng training–build–deploy đã được đánh giá bằng thực nghiệm đó.

**Slide hỗ trợ:** 11 và 19.

### Q3. Why does the title mention multi-model serving when you evaluate only one model? ⭐

**Trả lời tiếng Anh:**

> Multi-model serving describes the architectural scope: the platform manages multiple model projects and versions through shared services. Our evaluation uses one fixed classifier to isolate monitoring behavior. It does not establish performance under concurrent multi-model load. That requires a separate evaluation with several models and competing workloads.

**Giải thích tiếng Việt:** Thừa nhận rõ ranh giới kiến trúc và empirical evaluation. Không dùng ảnh nhiều Model Project trên giao diện làm bằng chứng scalability hoặc isolation.

**Slide hỗ trợ:** 6, 12 và 22.

### Q4. Dataset shift and predictive harm were already distinguished in prior work. What is new here? ⭐

**Trả lời tiếng Anh:**

> We agree that the distinction is established in prior work. Our contribution is the controlled quantification for these NIDS traffic mixtures, including prevalence changes, held-out attack families and monitoring sensitivity. We connect those observations to a version-associated lifecycle design. We do not claim to introduce the distinction itself.

**Giải thích tiếng Việt:** Công nhận tiền lệ, sau đó chỉ rõ đóng góp thực nghiệm cụ thể. Không nói “chúng tôi là người đầu tiên chứng minh drift khác harmfulness”.

**Slide hỗ trợ:** 2, 3, 13–18 và References.

### Q5. Have you shown that this framework improves model updates or retraining decisions? ⭐

**Trả lời tiếng Anh:**

> We have shown cases where an alert alone would provide incomplete evidence for a model update. This motivates reviewing distribution evidence together with labeled quality. We have not evaluated whether the proposed policy produces better updates, lower costs or fewer regressions. Those outcomes require a separate policy comparison.

**Giải thích tiếng Việt:** “Motivate” khác “prove effectiveness”. Không tuyên bố đã đo tiết kiệm GPU, tránh poisoning hoặc cải thiện accuracy sau retraining.

**Slide hỗ trợ:** 21–22.

## 3. Kiến trúc, registry và vận hành

### Q6. Why did you implement a Native Registry instead of relying entirely on MLflow?

**Trả lời tiếng Anh:**

> The Native Registry stores application lifecycle state in the Control Plane, including ownership, version identities and artifact links. It also connects versions to references and monitoring runs. MLflow and execution engines act as adapters. This is a platform integration choice; we do not claim that our registry is technically superior to MLflow's registry.

**Giải thích tiếng Việt:** Native Registry là phần quản lý domain state của nền tảng. Không cần phủ nhận khả năng MLflow, không bịa benchmark so sánh hai registry.

**Slide hỗ trợ:** 6–7.

### Q7. What is the purpose of separating the Control Plane and Execution Plane?

**Trả lời tiếng Anh:**

> The Control Plane manages access, lifecycle state and references to artifacts. The Execution Plane runs the workloads for building, training, serving and monitoring. This keeps lifecycle management separate from individual workload execution. Argo coordinates jobs, while their results update the state managed by the Control Plane.

**Giải thích tiếng Việt:** Trả lời theo trách nhiệm của từng plane. Kiến trúc phân tách chưa tự chứng minh fault tolerance hoặc throughput tốt hơn.

**Slide hỗ trợ:** 6.

### Q8. Why use Redpanda and asynchronous logging?

**Trả lời tiếng Anh:**

> The asynchronous path separates prediction handling from persistence of production records. After a successful prediction, an event goes to Redpanda and a consumer writes the record to PostgreSQL. This provides data for later monitoring. A successful prediction response alone does not confirm that the database write has completed.

**Giải thích tiếng Việt:** Mục đích là tách inference khỏi consumer persistence. Không cam kết “không bao giờ mất log”, exactly-once hoặc giảm latency bao nhiêu nếu chưa đo.

**Slide hỗ trợ:** 8; ảnh backup 26.

### Q9. Does a version UUID guarantee reproducible monitoring reports?

**Trả lời tiếng Anh:**

> A version UUID provides context, but it is not sufficient for full reproducibility. The current replay path reads recent version-scoped records, and reference identifiers do not by themselves guarantee immutable bytes. The offline study retains fixed membership manifests. Stronger production reproducibility would require frozen windows and immutable reference snapshots.

**Giải thích tiếng Việt:** Phân biệt identity, association và immutability. Không gọi mọi window production là immutable snapshot. Đây là giới hạn được paper nêu rõ.

**Slide hỗ trợ:** 6, 11, 22.

### Q10. Is retraining automatically triggered by a drift alert? ⭐

**Trả lời tiếng Anh:**

> An alert should request inspection. Our proposed policy also considers labeled quality and representative data before retraining. Promotion would need evaluation and operational checks, together with human review. The platform has a training execution path, but this study does not demonstrate a fully evaluated automatic adaptation loop.

**Giải thích tiếng Việt:** Có training workflow không có nghĩa đã chứng minh closed-loop adaptation. Không khẳng định review gates là certified enforcement.

**Slide hỗ trợ:** 9, 11, 21–22.

### Q11. Does PyTorchJob mean that only PyTorch models can be trained?

**Trả lời tiếng Anh:**

> In the architecture presented in the paper, PyTorchJob is the Kubernetes training resource used to launch the workload. The runner executes the user's Python training script inside the Pod. The resource name does not mean that the script must use PyTorch. Actual framework support still depends on the runtime and artifact contract.

**Giải thích tiếng Việt:** Giữ đúng paper sử dụng Training Operator v1/PyTorchJob. Không trộn bản Trainer v2 đang phát triển vào mô tả hệ thống đã công bố.

**Slide hỗ trợ:** 9.

### Q12. How do you handle security and tenant isolation?

**Trả lời tiếng Anh:**

> The Control Plane maintains project ownership and access checks. However, those checks do not sandbox uploaded code. Secure execution also requires restricted identities, network controls and resource limits, followed by adversarial testing. Tenant isolation is an architectural concern that we have not validated as a security guarantee in this study.

**Giải thích tiếng Việt:** Không đánh đồng owner checks, namespace hoặc container với cách ly hoàn chỉnh. Chưa có adversarial isolation benchmark trong paper.

**Slide hỗ trợ:** 6 và 22.

## 4. Dữ liệu và thiết kế thực nghiệm

### Q13. Why choose a fixed XGBoost classifier and train it only on BENIGN and DDoS? ⭐

**Trả lời tiếng Anh:**

> A fixed classifier lets us study monitoring behavior without changes introduced by retraining. Restricting training to BENIGN and DDoS creates a controlled contrast between familiar traffic and held-out attack families. This is an intentional baseline for the experiment, not a claim that the model is ready to detect all attack families in production.

**Giải thích tiếng Việt:** Held-out family là thiết kế có chủ đích. Thừa nhận model biết ít family nên sẽ có giới hạn generalization; nghiên cứu khảo sát tín hiệu monitoring quanh giới hạn đó.

**Slide hỗ trợ:** 12–13.

### Q14. Why not evaluate deep learning or several stronger classifiers?

**Trả lời tiếng Anh:**

> Our experiment focuses on the relationship between monitoring signals for one fixed classifier. Comparing many architectures would introduce another dimension beyond this scope. The results provide counterexamples under the stated setup, rather than a universal claim about every model. Extending the study to more classifiers is an important next step.

**Giải thích tiếng Việt:** Không nói XGBoost tốt nhất hoặc thay model sẽ không thay kết quả. Một classifier đủ cho counterexamples cụ thể, chưa đủ khái quát cho toàn bộ model families.

**Slide hỗ trợ:** 12 và 22.

### Q15. Where does the dataset come from, and how do you address leakage?

**Trả lời tiếng Anh:**

> We use a processed CICIDS2017 derivative with 209,844 retained rows and 52 numeric features. The training, development, reference and evaluation pools have no exact feature-vector overlap. This reduces direct duplicate leakage, but does not establish session independence or complete upstream lineage. Those remain limitations of the available data.

**Giải thích tiếng Việt:** Con số retained khác 209.865 dòng input trước lọc. Zero overlap chỉ cho exact vectors, không phải chứng minh các flow độc lập hoặc dữ liệu xử lý upstream không gây leakage.

**Slide hỗ trợ:** 12 và 22.

### Q16. How are the 120 windows constructed? Are they independent?

**Trả lời tiếng Anh:**

> We use two window sizes. For each size, S0 has 30 windows, while the six shifted settings each have five. That gives 120 windows overall. Sampling is without replacement within a window, but different windows can reuse the evaluation pool. These are repeated controlled draws, not independent traffic captures.

**Giải thích tiếng Việt:** Công thức: **2 × (30 + 6 × 5) = 120**. S1 có 3 setting, S2 có 3 setting. Không gọi 120 windows là 120 independent datasets hoặc 120 lần train model.

**Slide hỗ trợ:** 13–14.

### Q17. What is the difference between S1 and S2?

**Trả lời tiếng Anh:**

> S1 changes total attack prevalence while retaining the DDoS family seen during training. S2 keeps total attack prevalence at 30 percent but replaces attack rows with held-out families. At 25 percent replacement, those unfamiliar attacks occupy 7.5 percent of the entire window. The scenarios separate prevalence changes from attack-family composition changes.

**Giải thích tiếng Việt:** S2-r25 không phải 25% toàn bộ window. Với n=1.000: 700 BENIGN, 225 DDoS và 75 held-out attacks.

**Slide hỗ trợ:** 13.

### Q18. Is this an experiment on temporal concept drift? ⭐

**Trả lời tiếng Anh:**

> These experiments construct changes in traffic composition using sampled windows. The available derivative lacks the temporal information needed for a temporal drift study. We therefore do not claim to demonstrate concept drift over time, or that the classifier forgets DDoS. Lower aggregate recall reflects the increasing share of poorly recognized attack families.

**Giải thích tiếng Việt:** Tránh gọi S2 là bằng chứng P(Y given X) thay đổi theo thời gian. Mixture thay đổi làm aggregate quality giảm; model và weights không đổi.

**Slide hỗ trợ:** 13, 17 và 22.

## 5. Kiểm định thống kê và diễn giải kết quả

### Q19. What exactly does drift share measure?

**Trả lời tiếng Anh:**

> Drift share is the fraction of features flagged by the specified testing rule. In our offline protocol, a feature is flagged when its BH-adjusted p-value is below 0.05. The dataset alert compares that fraction with a separate threshold. Drift share depends on the feature set, sample size and detector; it is not a failure probability.

**Giải thích tiếng Việt:** Có hai ngưỡng khác nhau: **q < 0,05** cho feature và **rho ≥ 0,30** cho dataset ở principal setting. “98% feature bị flag” không có nghĩa “98% request sai” hoặc “drift severity là 98%”.

**Slide hỗ trợ:** 14.

### Q20. Why use KS tests and Benjamini–Hochberg correction?

**Trả lời tiếng Anh:**

> KS provides a common feature-wise comparison of numeric distributions. We use BH correction to account for testing many features within each window. However, this does not guarantee dataset-level false-alert control for dependent and tied features. The protocol also tests marginal distributions, so it can miss changes in relationships between features.

**Giải thích tiếng Việt:** Không gọi BH là bảo đảm false positive của toàn hệ thống bằng 5%. Các features có thể phụ thuộc, ties ảnh hưởng kiểm định. Multivariate detectors là hướng mở rộng, chưa được so sánh đầy đủ ở đây.

**Slide hỗ trợ:** 14 và 22.

### Q21. Why choose a principal threshold of 0.30? Could another threshold solve the problem?

**Trả lời tiếng Anh:**

> We fixed 0.30 as the principal setting and also examined 0.10, 0.50 and 0.70. We do not claim that 0.30 is universally optimal. At S2-r25 with 1,000 rows, lowering the threshold to 0.10 raises alerts from one to two out of five. This improves sensitivity in that case, but does not eliminate missed alerts.

**Giải thích tiếng Việt:** Không bịa lý do tối ưu nghiệp vụ hoặc tuning trên validation nếu không có bằng chứng. Thresholds đã định trước; không chọn lại detector/threshold sau khi biết kết quả để làm đẹp báo cáo.

**Slide hỗ trợ:** 18.

### Q22. Are the S1 alerts false positives because quality remains high?

**Trả lời tiếng Anh:**

> The input distribution really changes in S1, so those alerts correctly indicate a distribution difference. Stable predictive quality does not make them false distribution alerts. The point is that the alert does not establish predictive harm or a need to retrain. It answers a different question from labeled quality assessment.

**Giải thích tiếng Việt:** Đây là phân biệt quan trọng: **đúng về distribution** vẫn có thể **không kèm suy giảm quality**. Không gọi S1 là false alarm chỉ vì F1 cao.

**Slide hỗ trợ:** 15.

### Q23. Is the S2 recall loss simply caused by a model that cannot recognize unseen attacks? ⭐

**Trả lời tiếng Anh:**

> Yes, the restricted baseline recognizes the held-out families poorly. As their share increases, aggregate attack recall falls. Our contribution is not discovering that an incomplete classifier can fail. It is quantifying how the monitoring alerts behave alongside that loss, including cases where substantial recall loss accompanies few alerts.

**Giải thích tiếng Việt:** Thừa nhận phần hiển nhiên trước, rồi chuyển về câu hỏi được nghiên cứu. Không nói model bị “quên” hoặc held-out attacks ít là nguyên nhân duy nhất làm KS/BH không alert.

**Nếu cần giải thích thêm:**

> Aggregate attack recall is a weighted combination of recall on DDoS and recall on the held-out families. The composition changes while the classifier stays fixed.

**Slide hỗ trợ:** 16–17.

### Q24. Are five seeds enough, and what do the error bars represent?

**Trả lời tiếng Anh:**

> The error bars show sample standard deviation across five principal draws for each shifted setting, with one fixed model and reference. They describe sampling variation in this setup. They are not confidence intervals or variation across independently trained models. Five draws are a limitation, so we avoid broad population-level claims.

**Giải thích tiếng Việt:** Mean ± sample SD, không phải standard error hoặc 95% CI. S0 alert count dùng 30 windows mỗi size; principal mean/SD trong bảng dùng 5 principal seeds. Không suy diễn các SD bằng 0 do làm tròn thành dữ liệu tuyệt đối giống nhau.

**Slide hỗ trợ:** 15–18.

### Q25. Does zero alerts in S0 establish that the detector has no false alarms?

**Trả lời tiếng Anh:**

> It establishes zero observed BH alerts in the tested stable windows and thresholds. There are 30 stable windows per size. That finite result does not guarantee a zero false-alert rate on future traffic, other references or other models. More diverse data and additional repetitions would be needed to estimate general behavior.

**Giải thích tiếng Việt:** Chỉ phát biểu kết quả quan sát có điều kiện. Không nói S0 lúc nào quality cũng hoàn hảo: số được làm tròn trong bảng principal khác tổng hợp toàn bộ 30 stable draws.

**Slide hỗ trợ:** 18 và 22.

## 6. Service replay, nhãn và giới hạn vận hành

### Q26. Why do the offline and live monitoring results differ?

**Trả lời tiếng Anh:**

> They use different detectors and dataset thresholds. The offline study uses KS with BH correction. The service source pins Evidently 0.4.15 and uses its default feature tests, with a dataset threshold of 0.60. The replay therefore provides separate integration evidence, rather than an exact replication of the offline statistical protocol.

**Giải thích tiếng Việt:** Service dùng normalized Wasserstein cho numeric features có hơn 5 distinct values, Jensen–Shannon cho trường hợp còn lại, feature threshold 0,1 và không BH theo cấu hình source paper mô tả. Source pin không phải archived runtime inventory. Không gọi detector Evidently là KS/BH.

**Slide hỗ trợ:** 11, 14 và 19.

### Q27. How can operators measure quality if production labels arrive late?

**Trả lời tiếng Anh:**

> Distribution monitoring can operate without labels, but a claim about predictive quality needs ground truth. In this study, labels were available for scoring and withheld during inference. In production, obtaining representative labels would require a separate process, such as reviewed sampling. We do not claim that the platform automatically produces those labels.

**Giải thích tiếng Việt:** Tách rõ study có labels và vận hành production có delayed labels. Reviewed sampling là đề xuất cách làm, chưa phải pipeline gán nhãn đã được paper chứng minh. Không dùng prediction của chính model làm ground truth.

**Slide hỗ trợ:** 2, 11, 14 và 22.

### Q28. Do the 42 failed requests show that the system is unreliable? What did recovery prove? ⭐

**Trả lời tiếng Anh:**

> The replay encountered 42 HTTP failures during a worker interruption, which we report explicitly. After recovery, the high-DDoS window had 1,000 stored predictions from 1,042 attempts. This demonstrates final coverage for that replay. It does not establish general availability, exactly-once delivery or a unique cause for every failed request.

**Giải thích tiếng Việt:** Lỗi là 502/503; kết quả audit là final coverage, không phải reliability SLA. Đối chiếu exact 52-feature vectors cho replay, không có nghĩa retry identity được giữ xuyên suốt. S0 từng có lỗi lưu class 0 thành empty string; nếu được hỏi, dùng Q29.

**Slide hỗ trợ:** 19.

### Q29. How did you verify that the service predictions matched the offline model?

**Trả lời tiếng Anh:**

> The replay used identical model bytes and the same reference under separate version identities. Frozen inputs were matched to production records using their exact feature vectors. All four prediction sets matched the offline artifact. S0 had a consumer issue that stored class-zero predictions as empty strings; its scoring used UI predictions cross-checked against records, with that discrepancy disclosed.

**Giải thích tiếng Việt:** S1/S2 dùng post-fix DB predictions không còn blanks. Mỗi export có 1.000 unique prediction/request IDs. Browser không gửi handoff row ID nên audit dùng vectors; không suy ra exactly-once trên mọi traffic hoặc trùng vectors tương lai.

**Slide hỗ trợ:** 19; phần Controlled Service Replay trong paper.

### Q30. Have you measured scalability, latency or resource savings on production?

**Trả lời tiếng Anh:**

> The evidence presented here focuses on monitoring behavior and service integration. The four-window replay is not a scalability benchmark, and the reported failures do not establish an availability guarantee. We also have not measured savings from avoiding retraining. Production performance requires a separate workload definition, repeated measurements and an explicit resource configuration.

**Giải thích tiếng Việt:** Không lấy số CPU/RAM tức thời trong ảnh backup làm benchmark. Không trộn đợt đo production bổ sung tháng 11 với replay trong paper mà không trình bày provenance riêng. Nếu ban tổ chức hỏi số chưa có trên slide, không tự ước lượng.

**Slide hỗ trợ:** 22; backup 25–27 chỉ minh họa giao diện.

### Q31. Can another researcher reproduce these results?

**Trả lời tiếng Anh:**

> The retained experiment includes configuration, seeds, input and model hashes, and split and window membership manifests. A verification script recomputes predictions and the statistical tests. These support numerical checking with the frozen local input. They do not establish independent reconstruction from the upstream dataset, whose byte-level lineage remains incomplete.

**Giải thích tiếng Việt:** Có retained local evidence không đồng nghĩa mọi artifact đã public hoặc người ngoài có thể tái dựng input từ Kaggle. Chỉ chia sẻ link công khai sau khi xác nhận thật sự truy cập được.

**Slide hỗ trợ:** 12, 14 và 22.

### Q32. What would be the most important next experiment?

**Trả lời tiếng Anh:**

> I would evaluate the proposed review policy on temporally ordered data with delayed labels. The comparison should include an alert-only policy and a policy using both distribution and labeled quality. We would measure detection performance, update costs and regressions. A separate multi-model workload test would address serving scalability and resource contention.

**Giải thích tiếng Việt:** Đây là hướng tương lai, không phải kết quả đã có. Temporal evaluation/policy effectiveness và multi-model systems benchmark là hai bài đánh giá khác nhau.

**Slide hỗ trợ:** 21–22.

## 7. Bảng số liệu cần nhớ nhanh

| Nội dung | Số liệu/phạm vi cần nhớ |
|---|---|
| Dataset retained | 209.844 rows, 52 numeric features |
| Pools | Train 50%, Dev 10%, Reference 20%, Evaluation 20% |
| Fixed model | XGBoost; 200 trees, depth 6, learning rate 0,1; prediction threshold 0,5 |
| Train baseline | 74.994 BENIGN/DDoS rows; giữ PortScan, BruteForce, WebAttacks ngoài fitting |
| Reference | 5.000 rows; 70% BENIGN, 30% DDoS |
| Tổng windows offline | 120; n=500 và n=1.000 |
| Số windows mỗi size | S0: 30; mỗi shifted setting: 5; tổng 60 mỗi size |
| Offline detector | KS, BH-adjusted q < 0,05; principal dataset threshold 0,30 |
| Sensitivity thresholds | 0,10 / 0,30 / 0,50 / 0,70 |
| S1, n=1.000 | Drift share khoảng 0,742–0,981; 5/5 alerts mỗi setting; macro-F1 ≥ 0,9992 |
| S2-r25, n=1.000 | Recall 0,7533; mean drift share khoảng 0,165; 1/5 alerts tại 0,30 |
| S2-r25 composition | 700 BENIGN + 225 DDoS + 75 held-out attacks |
| S1-a85 so với S2-r100 | Drift share cùng khoảng 0,981; macro-F1 khoảng 0,999 so với 0,422 |
| Service replay | 4 windows riêng, mỗi window 1.000 rows; không phải 120 offline windows |
| Service detector | Source-pinned Evidently 0.4.15; dataset threshold 0,60; khác KS/BH |
| Replay S1-a85 | 43/52 flagged, alert, recall 1,0000 |
| Replay S2-r50 | 22/52 flagged, không alert, recall 0,5067 |
| Replay S2-r100 | 29/52 flagged, không alert, recall 0,0100 |
| Recovery S1 | 42 HTTP failures; 1.042 attempts; final 1.000 stored predictions |

Các mean/SD và alert counts phải đi cùng sample size và setting. Không dùng bảng này thay thế điều kiện trong paper.

## 8. Những cách nói cần tránh

| Tránh khẳng định | Cách nói chính xác hơn |
|---|---|
| “We invented the distinction between shift and harm.” | “We quantify the disagreement in controlled NIDS mixtures.” |
| “Our platform has proven multi-model scalability.” | “The architecture supports multiple model projects; concurrent load remains unevaluated.” |
| “S1 produces false drift alerts.” | “S1 changes the distribution while predictive quality remains high.” |
| “S2 proves temporal concept drift.” | “S2 constructs attack-family composition changes with a fixed classifier.” |
| “98% drift means 98% of predictions fail.” | “About 98% of features are flagged under the specified rule.” |
| “BH guarantees a 5% system false-alert rate.” | “BH adjusts feature-wise tests; dataset-level control is not established here.” |
| “Zero observed stable alerts means no future false alarms.” | “We observed zero alerts in the tested stable windows.” |
| “The framework automatically labels production data.” | “The study uses known labels for separate quality assessment.” |
| “We proved automatic retraining improves quality.” | “The results motivate reviewed updates; policy effectiveness remains unevaluated.” |
| “The replay proves exactly-once delivery.” | “The audit establishes final coverage for the replayed inputs.” |
| “The live test reproduces KS/BH results.” | “The replay uses a different detector and supplies integration evidence.” |
| “A version UUID guarantees immutable evidence.” | “A UUID supplies identity; frozen membership and immutable bytes require additional guarantees.” |

## 9. Câu tiếng Anh dùng khi cần làm rõ hoặc chưa có kết quả

**Xin nhắc lại câu hỏi:**

> Could you please repeat the last part of your question?

**Xác nhận mình hiểu đúng:**

> If I understand correctly, you are asking whether we evaluated the update policy itself.

**Khi câu hỏi nằm ngoài phạm vi đã đánh giá:**

> We have not evaluated that aspect in this study, so I cannot make a measured claim about it. It would require a separate experiment.

**Khi người hỏi chỉ ra một giới hạn hợp lý:**

> Yes, that is a limitation of the current evaluation. Our conclusion is restricted to the fixed model, reference and controlled windows used here.

**Khi muốn dùng slide backup:**

> I can show the workflow on the backup slide to clarify that point.

**Khi cần số chính xác chưa nhớ:**

> I would prefer to check the retained results rather than give an inaccurate number.

**Kết thúc một câu trả lời dài:**

> Does that address your question, or would you like me to explain the experimental setup in more detail?