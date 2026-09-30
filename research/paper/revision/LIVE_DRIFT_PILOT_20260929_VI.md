# Pilot drift trên cụm thật — 29/09/2026

## Phạm vi và nguồn dữ liệu

Đây là phép replay có kiểm soát từ bundle `research/paper/experiments/drift_only/handoff_exports/nids_replay`, seed 42. Model được phục vụ là cùng MLflow ZIP/XGBoost baseline ở mọi cửa sổ; SHA-256 của `baseline.ubj` là `bd0a91ec11d38ccceca4950a571857f3710bc7034bb8aaf30b40295dfd15e8b5`. Reference là `reference/features.csv`, 5.000 hàng, 52 feature, SHA-256 `b7f4d1ad4975539bb77b18cd05ef1da9406404ebbbbb032401cb6b9e837f59c3`. Nhãn chỉ được dùng sau inference để chấm điểm. Đây **không phải** natural/temporal drift của CIC-IDS2017.

## S0 — baseline 70% benign, 30% DDoS

| Bằng chứng | Kết quả |
|---|---:|
| Model version | `52dd7445-9b5f-409a-8e20-07aa87110279` |
| Model build | `9122355f-e3bb-4852-91d7-4957745a257e` |
| Request thành công/thất bại trên web | 1.000 / 0 |
| Production records cho riêng version | 1.000 |
| Prediction ID / request ID duy nhất | 1.000 / 1.000 |
| Ghép vector 52 feature với hàng replay | 1.000 / 1.000, không trùng hoặc thiếu |
| TN / FP / FN / TP | 700 / 0 / 0 / 300 |
| Attack recall / benign FPR / macro-F1 | 1,000 / 0,000 / 1,000 |
| Evidently run | `65c1e521-69d1-46f5-8e04-fe9e11bfe557`, completed |
| Feature drift | 1/52 = 0,0192 (`act_data_pkt_fwd`) |
| Ngưỡng và kết luận | 0,6; `has_drift=false` |

Auto trigger chạy sau khi Consumer ghi đúng 1.000 record; monitor có `trigger_threshold=1000` và `last_automatic_trigger_count=1000`. Argo Evidently job thành công, báo schema healthy: 52 feature chung, không thiếu/thừa/high-null. Đối chiếu `handoff_tools.py score` cho `prediction_mismatches=0` so với dự đoán offline của chính artifact này.

**Lỗi dữ liệu phát hiện khi audit:** Consumer bản cũ dùng `str(row.get("prediction") or "")`, khiến 700 dự đoán class `0` thành chuỗi rỗng trong database; 300 class `1` vẫn nguyên. Toàn bộ 1.000 giá trị 0/1 gốc còn trên testing console của giao diện. Audit đọc 1.000 giá trị đó theo thứ tự replay, ghép từng record theo vector feature duy nhất, và bác bỏ mọi bất đồng giữa UI và DB (ngoại trừ chuỗi rỗng đã chứng minh là lỗi class `0`). Do đó confusion matrix trên lấy từ **kết quả UI đã đối chiếu DB**, không phải từ bản ghi DB thô. File local `tmp/csonet_pilot_20260929/S0_ui_predictions.hex` lưu 1.000 bit UI theo thứ tự replay; `S0_v3_records.jsonl` là bản export thô; `audit_S0_n1000_s42.json`, `responses_S0_n1000_s42.csv`, `score_S0_n1000_s42.json` là các bước audit/chấm điểm. Các file trong `tmp/` chưa được đưa lên Git.

Lỗi đã sửa bằng PR #100; test hồi quy 6/6 pass. PR GitOps #101 chỉ promote tag image Consumer. Argo CD đã báo Synced/Healthy ở commit `c511d7d5d5ddcea9f742519d2dfb9fbeb6fce20e`, pod Consumer mới Running và rollout thành công. Các cửa sổ tiếp theo chỉ chạy sau khi xác nhận sửa lỗi trên cụm.

## S1 — kiểm tra vận hành và khôi phục replay

Project riêng `d44d94ee-3b69-4ffe-a833-4e8fe6d11376` phục vụ cùng model ở version `f3cc44ea-677d-4d63-a14b-aeb3d4fc62fa`; monitor `cfcc3dd5-002f-458a-aa7e-0849ba2d53d1` dùng cùng reference 5.000 hàng và trigger 1.000. Lượt đầu dừng sau 176 hàng: 134 thành công, 42 lỗi HTTP 502/503 liên tiếp ở hàng 68–109. Cùng thời điểm, `worker-node-2` báo `NodeNotReady` do kubelet ngừng cập nhật trạng thái; sau đó node trở lại `Ready`. Sự trùng thời gian và việc nhiều pod trên node khởi động lại phù hợp với lỗi hạ tầng, nhưng không đủ để quy nguyên nhân duy nhất cho mỗi request. Workflow build S2-r50 chạy đồng thời cũng thất bại do Kyverno webhook không có endpoint trong khoảng gián đoạn. Đây là **sự cố vận hành pilot**, không phải lỗi phân loại hay bằng chứng về hiệu năng mô hình.

Kiểm tra DB ở mốc 134 request thành công cho thấy nhãn `0`: 20 bản ghi, nhãn `1`: 114 bản ghi, không có nhãn rỗng; bản vá Consumer trên cụm đã có hiệu lực. CSV khôi phục `tmp/csonet_pilot_20260929/S1_a85_recovery_866.csv` gồm đúng 42 hàng lỗi và 824 hàng chưa gửi, không chứa nhãn. Chỉ chấp nhận S1 là cửa sổ 1.000 mẫu sau khi bản export của đúng model version có đủ 1.000 prediction/request ID duy nhất, từng vector 52 feature khớp một-một với handoff, và monitor hoàn tất. Không dùng các tỷ lệ tạm thời để suy diễn về drift hoặc recall.

**Kết quả sau khôi phục:** replay bù 866/866 thành công, 0 lỗi. DB có đúng 1.000 record cho version S1, 1.000 prediction ID và request ID duy nhất, 1.000 vector khớp một-một với S1 frozen; không còn bản ghi nhãn `0` rỗng. Auto monitor cập nhật watermark lên 1.000 và Evidently run `b8e19282-e11b-421f-bdc3-bbff059137f3` hoàn tất, schema 52 feature healthy, **43/52 feature drift = 0,8269**, `has_drift=true` tại ngưỡng 0,6. Đối chiếu ground truth tách riêng: **TN=150, FP=0, FN=0, TP=850**, attack recall 1,000; benign FPR 0,000; macro-F1 1,000; không có dự đoán khác baseline offline. Như vậy **drift đặc trưng mạnh trong S1 không kéo theo suy giảm chất lượng của model này trên cùng cửa sổ**. Đây là shift cơ cấu benign/DDoS được dựng có kiểm soát, không phải natural/temporal drift; kết luận chỉ áp dụng cho kịch bản này. Bằng chứng local: `S1_v1_records.jsonl`, `audit_S1_a85_n1000_s42.json`, `responses_S1_a85_n1000_s42.csv`, `score_S1_a85_n1000_s42.json` trong `tmp/csonet_pilot_20260929/`.

## S2-r50 — attack-family shift

Project riêng `0d219e43-464c-4bfe-be39-5f599bf4d095`, version `be077f82-2464-4121-85f5-dc3a1739f01f`, monitor `ed949ebf-6bfa-48a8-bf39-f4aff1dd5250`. Dùng đúng baseline ZIP và reference 5.000 hàng như S0/S1, trigger 1.000, không có production record trước replay. Lần build đầu thất bại khi Kyverno webhook mất endpoint trong sự cố worker-2; build lại thành công, deployment qua health check. Cửa sổ frozen gồm 700 BENIGN, 150 DDoS, 50 BruteForce, 50 PortScan, 50 WebAttacks; nhãn không được upload lên testing UI. Mục tiêu là kiểm tra liệu attack recall giảm khi thay họ tấn công và detector có cảnh báo ở ngưỡng 0,6 hay không. Chỉ ghi kết quả sau khi audit đủ 1.000 production record.

**Kết quả chất lượng model:** web gửi 1.000/1.000 request thành công, 0 lỗi; DB lưu đủ 1.000 bản ghi với 1.000 prediction/request ID duy nhất và 1.000 vector 52 feature khớp một-một; không có nhãn rỗng. TN=700, FP=0, FN=148, TP=152; attack recall=0,5067, benign FPR=0, macro-F1=0,7885, không có prediction khác baseline offline. Trong 150 DDoS, recall=1; ở 150 attack thuộc ba họ held-out, model chỉ bắt được 2 BruteForce (2/50), PortScan 0/50 và WebAttacks 0/50. Suy giảm recall tổng chủ yếu do **thay đổi thành phần họ tấn công so với miền đã học**, chưa chứng minh quan hệ $P(Y\mid X)$ biến đổi theo thời gian. Bằng chứng local: `S2_r50_v1_records.jsonl`, `audit_S2_r50_n1000_s42.json`, `responses_S2_r50_n1000_s42.csv`, `score_S2_r50_n1000_s42.json` trong `tmp/csonet_pilot_20260929/`. Evidently run `880fdad0-94fe-44fe-a538-deb39812110d` tự kích hoạt tại watermark 1.000.

**Kết quả detector live:** Evidently run trên hoàn tất, schema 52 feature healthy; **22/52 feature drift = 0,4231**, nên `has_drift=false` tại ngưỡng 0,6. Trong cửa sổ này, attack recall đã giảm từ 1,000 ở S0 xuống 0,5067 nhưng policy live không cảnh báo. Đây là một *missed performance degradation* của policy cảnh báo này trong kịch bản có kiểm soát, không chứng minh detector không hoạt động nói chung. Run ban đầu `Pending` khoảng 10 phút vì scheduler báo `Insufficient cpu` trên cả hai worker và Karpenter provisioner chỉ phù hợp `workload-type=training`, không cấp thêm worker. Tôi tạm scale **chỉ runtime S0 pilot đã audit xong** (`deploy-9122355f-e3bb-4852-91d7-4957745a257e`) về 0 replica, giải phóng 250m CPU request; pod Evidently lập tức được xếp lên worker-1 và hoàn tất. Runtime S0 đã được khôi phục về 1 replica sau pilot.

## S2-r100 — thay toàn bộ attack bằng ba họ held-out

Project riêng `1ee5be0d-d6a8-4eae-a35f-ac1997fcf28d`, version `4960b703-e419-4dd9-9a09-9c3954c66324`, monitor `ca944288-c8b7-43de-a446-f6391d6e4f7b`. Dùng cùng baseline ZIP, reference 5.000 hàng, 52 feature và trigger 1.000 như ba cửa sổ trên. Build `86885597-ef92-430c-b1ab-cebcf6b02ef6` và deployment qua health check. Cửa sổ gồm 700 BENIGN, 100 BruteForce, 100 PortScan, 100 WebAttacks, không có DDoS; nhãn không được đưa vào CSV replay. Trước replay, project/version có 0 production record.

Web gửi **1.000/1.000 request thành công, 0 lỗi**. DB có đúng 1.000 prediction, 1.000 prediction ID và request ID duy nhất, 1.000 vector 52 feature khớp một-một với cửa sổ frozen và không có nhãn rỗng. Đối chiếu nhãn sau inference: **TN=700, FP=0, FN=297, TP=3**; attack recall **0,0100**, benign FPR **0**, macro-F1 **0,4224**. Trong 300 attack held-out, chỉ 3/100 BruteForce được nhận diện; PortScan 0/100 và WebAttacks 0/100. Không có prediction khác kết quả offline của chính artifact này. Bằng chứng local: `S2_r100_v1_records.jsonl`, `audit_S2_r100_n1000_s42.json`, `responses_S2_r100_n1000_s42.csv`, `score_S2_r100_n1000_s42.json` trong `tmp/csonet_pilot_20260929/`.

Monitor tự kích hoạt tại watermark 1.000. Evidently run `70a5fd1f-1721-4d7e-8f50-19c0912776fc` hoàn tất, schema 52 feature healthy, **29/52 feature drift = 0,5577**, `has_drift=false` tại ngưỡng 0,6. Giao diện hiển thị drift score 55,8% và trạng thái Healthy. Đây là cửa sổ suy giảm mạnh mà **policy cảnh báo live hiện tại bỏ qua**. Không gọi đây là concept drift theo thời gian: mẫu được dựng bằng cách thay thành phần họ attack, nên có thể là domain/label-support shift. Nó kiểm tra khả năng policy phát hiện tác động lên model trong một tình huống có kiểm soát, không chứng minh quá trình suy giảm tự nhiên của traffic production.

## Đối chiếu pilot đã kiểm chứng

| Cửa sổ | Request thành công | Feature drift live | Cảnh báo ở 0,6 | Attack recall | Macro-F1 |
|---|---:|---:|---|---:|---:|
| S0 (70/30, DDoS) | 1.000/1.000 | 1/52 = 0,0192 | Không | 1,0000 | 1,0000 |
| S1 (15/85, DDoS) | 1.000/1.042 lượt HTTP; bù đúng 42 hàng lỗi hạ tầng | 43/52 = 0,8269 | Có | 1,0000 | 1,0000 |
| S2-r50 (30% attack, nửa họ held-out) | 1.000/1.000 | 22/52 = 0,4231 | Không | 0,5067 | 0,7885 |
| S2-r100 (30% attack, toàn bộ held-out) | 1.000/1.000 | 29/52 = 0,5577 | Không | 0,0100 | 0,4224 |

S1 cho thấy cảnh báo phân phối không tự nó là căn cứ retrain; S2-r50 và S2-r100 cho thấy policy chỉ dựa trên share feature drift và ngưỡng 0,6 có thể bỏ qua tổn hại recall lớn. Đây là bốn cửa sổ dựng từ cùng derivative CICIDS2017, không phải bốn môi trường thực địa độc lập. Một seed mỗi kịch bản chỉ minh họa luồng end-to-end và **không thay thế** thống kê nhiều seed trong bảng offline.

**Độ nhạy quyết định cảnh báo trên chính bốn drift score đã đo:** nếu giữ nguyên detector và chỉ áp lại quy tắc `score >= threshold`, ngưỡng 0,4 sẽ cảnh báo S1, S2-r50, S2-r100; ngưỡng 0,5 cảnh báo S1 và S2-r100; ngưỡng 0,6 chỉ cảnh báo S1. S0 không cảnh báo ở cả ba ngưỡng. Đây là phép đối chiếu *hậu nghiệm* trên bốn điểm, không phải hiệu chỉnh ngưỡng hợp lệ hoặc ước lượng precision/recall của một policy triển khai. S1 là drift thật theo phép đo nhưng không suy giảm recall, nên phải kết hợp ground truth/model performance trước quyết định retrain.

## Giới hạn diễn giải

S0 chỉ kiểm tra pipeline baseline từ request đến persistence và Evidently. Điểm mô hình hoàn hảo trên cửa sổ này không chứng minh khả năng khái quát, không chứng minh drift tự nhiên, và không chứng minh chất lượng vận hành ở tải cao. Để trả lời Reviewer 1 cần so S1/S2 cùng model/reference, đo cả drift score lẫn recall/F1; đặc biệt tìm trường hợp drift nhưng không suy giảm, và suy giảm nhưng detector không cảnh báo. Mỗi cửa sổ phải dùng version/project riêng vì detector đọc các record mới nhất theo version và có thể trộn mẫu nếu replay chung.

**Không gộp số drift live vào bảng offline hiện tại:** paper dùng KS hai phía với hiệu chỉnh Benjamini--Hochberg và ngưỡng chính 0,30, còn monitor triển khai đang chạy Evidently preset mặc định (`detector_config={}`) với ngưỡng 0,60. Chúng là hai detector/decision policy khác nhau. Nếu đưa pilot này vào camera-ready, phải ghi riêng cấu hình live và giải thích vì sao tỷ lệ feature drift có thể khác bảng offline, dù dùng cùng cửa sổ/reference. Không chọn lại ngưỡng sau khi xem kết quả để tạo cảnh báo mong muốn.

## Trạng thái cụm sau pilot

Để dành CPU cho monitor, runtime S0 và S1 từng được hạ tạm về 0 replica. Sau khi cả bốn cửa sổ đã có kết quả, tôi hạ **hai runtime S2 vừa tạo** (`deploy-6b2517fe-7725-413d-a47b-5c8ac248a8e0`, `deploy-86885597-ef92-430c-b1ab-cebcf6b02ef6`) về 0 và khôi phục S0 (`deploy-9122355f-e3bb-4852-91d7-4957745a257e`) cùng S1 (`deploy-8c0507ed-de63-41c5-83a8-1fca09c19472`) về 1. Kiểm tra cuối cho thấy S0/S1 đều 1/1 Ready, S2-r50/S2-r100 0 replica; các model version, prediction records và Evidently reports còn lưu. Muốn gọi lại endpoint S2, scale runtime tương ứng về 1 và xác nhận Ready trước khi thử. Các deployment khác không bị chỉnh trong bước dọn pilot này.

## Đánh giá như reviewer và việc nên làm cho camera-ready

Pilot là bằng chứng tốt hơn ảnh chụp dashboard đơn lẻ: cùng một artifact/reference được replay qua serving, persistence và Evidently; có kiểm tra đủ mẫu, ID duy nhất, vector đầu vào và nhãn giữ riêng. S1 cho thấy drift không đồng nghĩa với suy giảm, trong khi S2-r50 và S2-r100 cho thấy suy giảm mạnh nhưng ngưỡng live 0,6 không cảnh báo. Đây là minh họa cụ thể cho luận điểm cần tách “bằng chứng phân phối”, “bằng chứng hiệu năng có nhãn” và quyết định lifecycle.

Giới hạn vẫn quan trọng: cửa sổ được dựng từ cùng derivative CICIDS2017, chỉ một seed live mỗi kịch bản, một model/tenant, và không có chiến lược retrain/rollback đối chứng hoặc drift theo thời gian. Sự cố worker trong S1 cũng cho thấy chưa thể dùng pilot để tuyên bố reliability/scalability. Với hạn 30/09, chỉ nên đưa vào paper như **pilot end-to-end có kiểm soát** nếu còn chỗ, trình bày tách biệt khỏi kết quả KS/BH offline và tránh gọi là natural drift hay proof of continuous training. Ưu tiên kiểm tra giới hạn trang/citation integrity, bổ sung artifact provenance và đối chiếu từng claim trước nộp; các benchmark đa tenant, temporal shift và retraining comparison cần được đánh dấu là chưa làm nếu không có số liệu thật.
