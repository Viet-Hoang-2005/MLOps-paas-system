# Chỉnh sửa camera-ready theo ARS — 30/09/2026

## Kết quả

- Đã sửa đúng manuscript `research/paper/A_Drift-Aware_MLOps_Framework_for_Multi-Model_Serving_CSONET.tex` trong worktree `mlflow-zip-upload`.
- Giữ title, tác giả, funding acknowledgement và disclosure hiện tại.
- Giữ nguyên nội dung ba bảng offline: scenarios, main results và threshold sensitivity. Không thay đổi frozen experiment artifacts.
- Bản cuối **8 trang**, template LNCS local `llncs 2024/01/29 v2.24`; không giảm font, đổi lề hoặc dùng negative spacing để ép trang.
- Bổ sung bảng live replay; thay sơ đồ kiến trúc cũ bằng mô tả rõ implementation, identity và proposed semantics. Bảng trạng thái kiến trúc thử ở lượt đầu đã chuyển thành văn xuôi để đủ 8 trang.
- Có 16 bibliography entries; mọi citation đều được định nghĩa và sử dụng. Không có reference chưa giải quyết hoặc overfull box ở bản cuối.
- Còn một underfull hbox nhẹ (`badness 1028`) trong entry HarmonE. Cảnh báo `epstopdf: Shell escape feature is not enabled` do chủ động tắt shell escape; manuscript không dùng EPS.
- Compile tích hợp đã được gọi nhưng không hoạt động do `Unable to find standard directories for platform`. Đã compile thành công bằng MiKTeX có sẵn, hai lượt, trực tiếp cùng source và PDF; không cài thêm công cụ.
- Đã xem bản render đủ 8 trang: bảng, công thức, references và credits không bị cắt/tràn.

Đây là lượt **revision và kiểm chứng tập trung**, không phải một review tổng quát mới hoặc xác nhận production readiness.

## Kế hoạch đã áp dụng

| Phần | Mục tiêu | Căn cứ | Cân đối trang |
|---|---|---|---|
| Abstract/Introduction | Đặt controlled study làm đóng góp được đánh giá chính | S1/S2, số liệu giữ nguyên | Rút câu giới hạn lặp |
| Related Work | So sánh cụ thể với nghiên cứu gần | Publisher/institutional sources đã kiểm tra | Thêm 3 refs, rút phần liệt kê chung |
| Framework | Tách defines/implements/evaluates | Models, drift reader và audit code | Dùng các paragraph rõ trạng thái thay sơ đồ/bảng dài |
| Reproducibility | Chỉ rõ artifact và giới hạn acquisition | Manifest, memberships, hashes, verifier | Thay đoạn cũ |
| Service replay | Làm rõ dữ liệu chấm điểm và detector live | Audit records, stored reports, service source, pinned library | Bảng 4 window và mô tả gọn |
| Discussion/Conclusion | Kết nối counterexamples với review semantics | Bằng chứng có kiểm soát | Gom hạn chế thay vì lặp ở mọi mục |

## M1 — Contribution positioning và Related Work

**Đã sửa:**

- Không trình bày “drift khác degradation” như phát hiện mới.
- Phân biệt đóng góp thực nghiệm, thiết kế lifecycle và bằng chứng tích hợp prototype.
- Đặt câu hỏi chính là khi nào alert và labeled quality đồng thuận hoặc bất đồng trên composition đã dựng.
- Định nghĩa degradation trong nghiên cứu này là chất lượng thấp hơn trên composition thay đổi, không phải suy giảm theo thời gian.
- Giữ S1: alert với chất lượng gần như không đổi; S2: recall thấp hơn nhưng tested monitor có thể không phát dataset alert.
- Nhấn rằng 25% replacement của attack chỉ chiếm 7,5% toàn window; giữ mixture explanation và toàn bộ kết quả định lượng cũ.
- Giữ title vì Introduction/Framework phân định rõ multi-model là architectural scope; không gọi pilot một classifier là multi-model validation.

**Nguồn đã xác minh trước khi thêm citation:**

| Citation | Metadata đã kiểm tra | So sánh được nguồn hỗ trợ |
|---|---|---|
| Rabanser, Günnemann, Lipton, *Failing Loudly* | NeurIPS 2019, volume 32; [publisher](https://papers.neurips.cc/paper_files/paper/2019/hash/846c260d715e5b854ffad5f70a516c88-Abstract.html) | Detection, characterization và shift harmfulness là các câu hỏi phân biệt |
| Sridhar et al., *Model Governance* | USENIX ATC 2018, pp. 351–358; [publisher](https://www.usenix.org/conference/atc18/presentation/sridhar) | Governance và provenance của production predictions |
| Leest, Raibulet, Lago, Gerostathopoulos, *From Tea Leaves to System Maps* | IEEE TSE 51(12), 3218–3246 (2025), DOI `10.1109/TSE.2025.3602520`; [institutional version of record](https://research.vu.nl/ws/portalfiles/portal/466350501/From_Tea_Leaves_to_System_Maps_A_Survey_and_Framework_on_Context-Aware_Machine_Learning_Monitoring.pdf) | Context để diễn giải monitoring và hành động |
| Bhatt et al., *HarmonE* — citation đã có | arXiv `2505.13693v1`, 2025; [source](https://arxiv.org/abs/2505.13693) | Accuracy, energy, distribution monitoring để hỗ trợ adaptation |

Không suy diễn rằng các nền tảng khác thiếu một capability chỉ vì prototype của nhóm có capability đó. Lượt này kiểm tra metadata/content của citation mới và HarmonE; không phải tái audit toàn bộ full text của mọi reference cũ.

## M2 — Native Registry semantics

**Đã sửa:** Framework gồm các mục `Implemented foundation`, `Defined and evaluated scope`, `Distribution evidence`, `Proposed review semantics`.

**Bằng chứng repo:**

- `services/control-plane/src/apps/catalog/models.py`: project ownership; asset UUID, URI, checksum tùy chọn.
- `services/control-plane/src/apps/registry/models.py`: model-version UUID, project association, artifact records.
- `services/control-plane/src/apps/drift/models.py`: monitor→version/reference; run UUID/status/report URIs; snapshot/evidence-window links tùy chọn.
- `services/evidently/src/data.py`: lấy các record mới nhất theo model-version UUID, không mặc định tạo frozen membership manifest.
- `research/paper/experiments/drift_only/audit_live_window.py`: external reconciliation cho pilot.

**Giới hạn ghi đúng trong bài:** trường UUID/link không tự bảo đảm reference bytes bất biến, membership đóng băng hoặc tính đúng khi concurrent update. Điều kiện review, quality gate và promotion là proposed semantics trong phạm vi paper; không khẳng định đã được invariant/failure tests chứng minh.

BH-adjusted p-values `q_j` và drift share được định nghĩa rõ. Drift share là tỷ lệ feature bị gắn cờ, không phải severity, tỷ lệ request bị ảnh hưởng hoặc xác suất model failure.

## M3 — Reproducibility

**Artifact root được kiểm tra:** `research/paper/experiments/drift_only/`.

| Thành phần | File trong artifact root |
|---|---|
| Input checksum, exclusions, ordered feature schema | `results/run_20260926/dataset_manifest.json` |
| Model checksum/config metadata | `results/run_20260926/model_manifest.json`, `baseline.ubj`, `config.json` |
| Split membership | `results/run_20260926/split_manifest.csv.gz` |
| Reference/window membership | `reference_manifest.csv`, `window_membership.csv.gz` trong cùng run |
| Raw metrics/tests | `window_metrics.csv`, `feature_drift.csv.gz` |
| Summary tables | `scenario_summary.csv`, `threshold_summary.csv` |
| Environment và seeds | `environment.json`, `config.json` |
| Separate verifier | `verify_results.py`, retained `results/run_20260926/verification.json` |
| Format main table | `research/paper/revision/build_result_assets.py` — ngoài artifact root |

**Kiểm tra bổ sung trong lượt này:**

- Input local SHA-256 khớp `0728925d293f433a3f7bce4509c00e1648906c59c59d8e63663e1622a226ef6c`.
- Model SHA-256 khớp `bd0a91ec11d38ccceca4950a571857f3710bc7034bb8aaf30b40295dfd15e8b5`.
- Ordered schema 52 feature khớp giữa dataset và model manifests.
- 209.844 row assignments có feature hash duy nhất; reference 5.000 row thuộc reference pool; window membership thuộc evaluation pool.
- Có 120 window metrics; 59 file trong handoff bundle khớp checksums.
- Không tái chạy 6.240 KS tests trong lượt này. Bài ghi chính xác rằng retained verification record báo pass, không gọi đó là một lần kiểm chứng độc lập mới.

**Chưa giải quyết:** public artifact access và versioned input acquisition. Không thêm GitHub URL của repo sản phẩm, không viết “fully reproducible” hoặc “available upon request”. Phân biệt numerical checks từ frozen local input với tái tạo độc lập từ Kaggle; không cho rằng deduplication giải quyết upstream leakage.

## M4 — Live service replay

**Bằng chứng:** report `research/paper/revision/LIVE_DRIFT_PILOT_20260929_VI.md`; audit code; các file audit, scoring, responses, raw exports và S0 UI bitstream local trong `tmp/csonet_pilot_20260929/` của checkout chính. Raw exports không được sao chép vào report này.

| Window | Căn cứ prediction | Đối soát | TN/FP/FN/TP |
|---|---|---|---|
| S0 | UI console, cross-check DB; 700 class-0 từng thành empty string | 1.000 record, ID và feature matching | 700 / 0 / 0 / 300 |
| S1 85% DDoS | DB sau bản sửa, không blank | 1.000 record, ID và feature matching | 150 / 0 / 0 / 850 |
| S2 r50 | DB sau bản sửa | 1.000 record, ID và feature matching | 700 / 0 / 148 / 152 |
| S2 r100 | DB sau bản sửa | 1.000 record, ID và feature matching | 700 / 0 / 297 / 3 |

Đã chạy lại audit local cho cả 4.000 record. Outputs khớp các CSV responses đã lưu; confusion matrices tính lại khớp score files; prediction từng dòng khớp frozen expected predictions trong handoff.

**Làm rõ trong manuscript:**

- Browser không gửi handoff row ID: ghép bằng feature vector IEEE-754 chính xác, không gọi request ID là retry-idempotency guarantee.
- S0 được chấm từ 1.000 UI predictions, chỉ cho phép bất đồng DB empty-string/UI zero đã biết.
- S1 phục hồi 42 failed inputs và 824 unsent inputs; tổng 1.042 attempts để có 1.000 final records. Không gán một root cause duy nhất cho mọi HTTP failure.
- Dataset threshold live là 0.60; giữ nguyên counts 1/52, 43/52, 22/52, 29/52 và recall.
- Service source pin `evidently==0.4.15`, gọi `DataDriftPreset` không feature override; không BH.
- Đối chiếu source thư viện 0.4.15 có sẵn trong local venv: reference trên 1.000 row dùng normalized Wasserstein cho numerical columns có trên 5 distinct values, Jensen–Shannon cho trường hợp còn lại; thresholds tương ứng 0.1. Đã đọc `_get_default_stattest`, `_wasserstein_distance_norm` và `_jensenshannon`.
- Nêu đây là source-defined configuration, không phải archived dependency inventory của container pilot. Không khẳng định đã kiểm tra trực tiếp version runtime lịch sử.
- Phân biệt rõ live preset với offline KS/BH. Không gọi live replay là replication của cùng detector.

## Những điểm vẫn cần nhóm quyết định hoặc bổ sung bằng chứng

1. **M3:** Chưa có phương thức public access/versioned acquisition được xác lập. Có frozen artifacts local không đồng nghĩa bên ngoài có thể tái lập ngay.
2. **M4:** Chưa có archived runtime inventory hoặc report-level per-feature configuration đủ để chứng thực chính xác toàn bộ dependency đã chạy live. Không tái chạy hoặc truy cập cluster trong lượt này.
3. **M4:** Có thể kiểm tra tính nhất quán của S0 UI bitstream và DB export local, nhưng không xác thực độc lập quá trình thu UI bitstream từ dữ liệu đã lưu.
4. **M2:** Không có bằng chứng trong nghiên cứu này để chứng nhận invariant dưới concurrency/failure hoặc hiệu quả promotion/retraining policy. Bài giữ đây là design requirements/proposed semantics.

Các thiếu hụt này được ghi thành giới hạn; không được lấp bằng claim mới hoặc kết quả bịa.

## Focused self-audit

| Câu hỏi | Kết luận |
|---|---|
| Đóng góp trung tâm đã rõ? | Có: controlled disagreement study trước, design/integration hỗ trợ |
| Nguyên lý đã biết bị gọi là mới? | Không; đối chiếu trực tiếp prior work |
| Design intent bị gọi là verified behavior? | Không; có cảnh báo optional identities và unevaluated policy |
| Architectural scope bị gọi là validated multi-model serving? | Không; một classifier được nêu rõ |
| Có unsupported production/retraining/scalability claim? | Không phát hiện trong bản cuối |
| Người đọc hiểu S1/S2? | Có; prevalence shift, held-out mixture, dilution và mixture recall được giải thích |
| Người đọc biết tái lập được tới đâu? | Có; frozen local checks khác public dataset reconstruction |
| Số liệu gốc có bị đổi? | Không; ba bảng offline được so sánh byte-for-byte với bản gốc |

## Kiểm tra kỹ thuật

Xem `BUILD_VERIFICATION.json` và `ARS_REVISION_EVIDENCE_2026-09-30.json` để biết hashes và kết quả kiểm tra. Manuscript vẫn chứa đủ nội dung trong một file `.tex`, không thêm `\input` phụ thuộc. Các style files LNCS vẫn là yêu cầu của project LaTeX như trước.

Chưa commit hoặc push trong lượt revision này.
