# Bàn giao replay drift NIDS qua Git

**Nhánh:** `codex/csonet-2026-camera-ready`. Không cần gửi lại dataset nếu hai máy có đúng `data/reference_data.csv`. Không train lại, không chia lại dữ liệu và không thay model bằng model production khác.

## 1. Nhận code và xuất bộ replay

Tại repository của bạn, lấy nhánh bằng quy trình Git thông thường. Nếu chưa có nhánh local và working tree đã sẵn sàng để chuyển nhánh:

```powershell
git fetch origin
git switch --track origin/codex/csonet-2026-camera-ready
```

Nếu đã ở nhánh đó, cập nhật bằng `git pull --ff-only origin codex/csonet-2026-camera-ready`. Không reset hoặc ghi đè các thay đổi riêng của bạn.

Từ repository root, trong môi trường Python riêng:

```powershell
python -m pip install -r research/experiments/drift_only/requirements-handoff.txt
python research/experiments/drift_only/export_handoff.py --with-mlflow
```

Script kiểm tra checksum nguồn trước khi xuất. SHA-256 bắt buộc:

```text
0728925d293f433a3f7bce4509c00e1648906c59c59d8e63663e1622a226ef6c
```

Nếu khác checksum, dừng và lấy đúng bản từ nhóm; không bỏ kiểm tra hoặc tự sửa manifest. Dùng `--source "đường dẫn/reference_data.csv"` nếu dữ liệu ở chỗ khác. Script không cần các CSV khác trong `data/`.

Đầu ra mặc định: `research/experiments/drift_only/handoff_exports/nids_replay/`. Thư mục này được gitignore vì chứa dữ liệu xuất, không cần push. Script từ chối ghi đè thư mục đã có; muốn xuất lại hãy dùng `--output "đường dẫn mới"`.

Không có `--with-mlflow` thì chỉ xuất model UBJ và bộ dữ liệu; chưa có gói MLflow để worker load. Runtime đóng gói và runtime detector nên dùng môi trường riêng: Evidently replay đã khóa ở 0.4.15, pandas 2.0.3, NumPy 1.26.4; toàn bộ môi trường detector nằm trong `provenance/evidently_environment.lock.txt` của output. Không nâng Evidently theo môi trường xuất model.

## 2. Dùng file nào?

| Đường dẫn bên trong output | Mục đích |
|---|---|
| `manifest.json` | Danh sách 12 cửa sổ, pilot/extension, schema, hashes và cấu hình |
| `model/baseline.ubj` | Model gốc bất biến |
| `model/mlflow/` | Gói MLflow để đưa vào quy trình build/register đang có; được tạo khi dùng `--with-mlflow` |
| `model/mlflow.zip` | ZIP sẵn để upload bằng Model Package; đường dẫn metadata được chuẩn hóa cho Linux |
| `model/features.json` | Đúng 52 feature và thứ tự |
| `reference/features.csv` | Reference 5000 dòng, chỉ có feature |
| `windows/<window_id>/features.csv` | 1000 dòng input/window, chỉ có feature |
| `windows/<window_id>/requests.jsonl` | Request body đã chuẩn bị và ID để nối kết quả |
| `scoring/<window_id>.csv` | Row ID, family, ground truth, expected prediction/probability; **không upload như input/reference** |
| `expected/window_metrics.csv` | Chất lượng offline đã kiểm tra lại với kết quả khóa |
| `expected/evidently_windows.csv` | Drift share/alert kỳ vọng từ library replay, không phải đo qua service |
| `expected/evidently_features.csv` | Statistic, threshold và drift flag từng feature |
| `expected/family_counts.csv` | Support, predicted attack, missed attack theo family |
| `checksums.json`, `handoff_tools.py` | Kiểm tra tính toàn vẹn và chấm kết quả trả về |

`source_row_id` là số dòng dữ liệu gốc bắt đầu từ 0, không tính header. `replay_index` là vị trí bắt đầu từ 0 trong từng CSV xuất. Các cửa sổ có thể trùng mẫu với nhau; reference không trùng evaluation.

Gói MLflow trả nhãn số **0=BENIGN, 1=ATTACK**, sử dụng `P(ATTACK) >= 0.5`; không scaler. Script kiểm tra 12000 dự đoán của gói MLflow bằng model gốc trước khi báo hoàn thành. Điều này là kiểm tra đóng gói offline, chưa chứng minh chạy qua endpoint thành công.

## 3. Thứ tự benchmark

Chạy 4 cửa sổ pilot trước:

```text
S0_n1000_s42
S1_a85_n1000_s42
S2_r50_n1000_s42
S2_r100_n1000_s42
```

Nếu input/logging/report parity đạt thì chạy cùng 4 scenario với seeds 123 và 456. Tổng 12 cửa sổ, 12000 inference hợp lệ; không phải benchmark tải. Không lấy mean của bộ 3 seeds này rồi gọi là bảng 5 seeds của paper.

Cho từng cửa sổ:

1. Gắn model và reference cố định; cô lập production data theo model version hoặc cơ chế window đã xác minh. Không tích lũy các scenario vào cùng tập dữ liệu mà detector đọc.
2. Đọc từng dòng JSONL. **Chỉ gửi đối tượng `body` làm JSON body HTTP**. `request_id`, `replay_index`, `source_row_id` là metadata bên ngoài, không đưa vào features. Có thể dùng `request_id` cho header `X-Request-ID`; lưu lại ID response thực tế. Không nhúng endpoint/token vào file.
3. Lưu response, prediction ID và nhãn dự đoán theo replay_index. Nếu request thất bại hoặc retry, ghi nhận đầy đủ; không âm thầm tạo duplicate rồi chấm một tập con thành 1000 mẫu.
4. Kiểm tra database chứa đúng 1000 mẫu tương ứng, đúng model version. Smoke request ở tập riêng. Nếu auto-trigger đã chạy trên tập chưa đủ/khác mẫu, ghi rõ và tạo report kiểm soát đúng window; không gọi manual report là auto-trigger đã được xác minh.
5. Detector dùng đúng 5000 reference rows và 52 feature. `dataset drift threshold=0.6` khác với ngưỡng số samples để kích hoạt job. Không fallback lấy production làm reference. Label, prediction và ID không được tính thêm vào mẫu số 52 feature.
6. Thu report/summary JSON, per-feature statistic và flag, run ID, model-version UUID, image digest, callback status và đối chiếu `expected/`.

Giữ bản raw responses để audit. API có thể trả `confidence` là xác suất của lớp dự đoán dưới dạng phần trăm; **không coi confidence là P(ATTACK)**. Chấm nhãn binary trực tiếp; chỉ đối chiếu attack probability nếu API cung cấp đúng đại lượng đó.

## 4. Kiểm tra output sau xuất hoặc sau sao chép

Từ repository root:

```powershell
python research/experiments/drift_only/handoff_tools.py verify --bundle research/experiments/drift_only/handoff_exports/nids_replay
```

Hoặc đứng trong output đã sao chép: `python handoff_tools.py verify --bundle .`. Lệnh chỉ cần Python standard library, kiểm tra checksum, row hashes, 52 feature, thứ tự, label mapping, requests và overlap reference. Không cần dataset gốc để xác minh bundle đã xuất.

## 5. Chấm prediction của hệ thống

Chuyển response thực tế thành CSV cho từng cửa sổ, có header:

```text
window_id,replay_index,prediction_id,pred_binary
```

`pred_binary` phải là 0/1 theo mapping đã nêu; ID phải đến từ response thật, không lấy dự đoán kỳ vọng để điền kết quả đo. Mỗi file đủ 1000 replay_index duy nhất 0–999 và prediction_id duy nhất. Giữ mapping về raw response. Sau đó:

```powershell
python research/experiments/drift_only/handoff_tools.py score --bundle research/experiments/drift_only/handoff_exports/nids_replay --window S0_n1000_s42 --responses responses_S0_n1000_s42.csv --output score_S0_n1000_s42.json
```

Script từ chối window thiếu mẫu/trùng ID/lẫn scenario và từ chối ghi đè output. Kết quả có TN/FP/FN/TP, recall, FPR, macro-F1, lỗi theo family và số dự đoán khác offline. Lệnh này chỉ chấm file prediction; database coverage, drift report và callback phải audit riêng.

## 6. Gửi lại cho người viết paper

- Raw requests/responses và mapping row → request → prediction ID, kèm danh sách lỗi/retry.
- Kết quả chấm từng window; không chỉ screenshot.
- Audit production/reference membership, scope và số feature.
- Drift JSON/summary/per-feature flags; model-version/run IDs và versions/image digest.
- Bảng window nào hoàn tất, parity nào đạt/khác và lý do; không loại cửa sổ kết quả xấu.

Plan đầy đủ trong repo: `docs/paper/csonet_2026_one_week_drift_plan_vi.md`, đặc biệt mục 9 và 11–14. Chạy thành công script xuất hoặc kiểm tra gói **không phải** đã hoàn thành service benchmark. Không có lệnh nào ở đây tự deploy, gửi request hoặc kích hoạt retraining.
