# Evidently Service — Data Drift Detection Worker

Evidently Service là container thực thi phân tích **Data Drift** theo mô hình **isolated job** — được kích hoạt bởi Argo Workflows và chạy trong K8s cluster. Không expose HTTP API, chỉ đọc dữ liệu, phân tích, upload kết quả, và gửi webhook callback.

---

## Vai Trò

- **Phát hiện Data Drift**: So sánh phân phối của **Production Data** (dữ liệu inference thực tế trong PostgreSQL) với **Reference Data** (dữ liệu huấn luyện chuẩn trên S3) bằng thư viện Evidently AI.
- **Schema-Flexible Analysis**: Tự động flatten cột `features` dạng `JSONB` từ PostgreSQL thành Pandas DataFrame — không cần hardcode số lượng feature.
- **Báo cáo tự động**: Xuất báo cáo HTML trực quan và JSON Summary, upload lên S3.
- **Webhook Callback**: Sau khi phân tích, gửi kết quả (`drift_score`, S3 URLs) về Control Plane qua HTTP POST.
- **Runtime Log Stream**: Mirror stdout/stderr vào Redis key `drift_logs:{DRIFT_RUN_ID}` để Control Plane hiển thị tiến trình theo thời gian thực.

---

## Luồng Hoạt Động

```
Argo Workflows kích hoạt evidently-workflowtemplate
  ↓
1. Tải Reference Data từ S3 (presigned URL do Control Plane cấp)
2. Query Production Logs từ PostgreSQL theo model_version_id + tenant_id
3. Flatten JSONB features → Pandas DataFrame
4. Chạy Evidently DataDriftPreset
5. Xuất report.html + summary.json
6. Upload lên S3:
   - drift-reports/{job_id}/report.html
   - drift-reports/{job_id}/summary.json
7. POST webhook → Control Plane:
   {"drift_score": 0.72, "status": "drifted", "html_url": "...", "summary_url": "..."}
```

---

## Cấu Trúc Thư Mục

```
src/
├── main.py         # Process entrypoint and exit-code handling
├── application.py  # Orchestration of one drift run
├── config.py       # Runtime validation
├── data.py         # Reference/production data acquisition and normalization
├── analysis.py     # Evidently column-mapping helpers
└── reporting.py    # Result callback delivery
```

---

## Công nghệ

| Thành phần | Công nghệ |
|---|---|
| Drift Analysis | `evidently` (DataDriftPreset, DataQualityPreset) |
| Data Processing | `pandas`, `sqlalchemy` |
| Storage | `boto3` S3 |
| Database | PostgreSQL (JSONB features) |

---

## Biến Môi Trường

| Biến | Mô tả |
|---|---|
| `JOB_ID` | ID của DriftJob trên Control Plane |
| `DRIFT_RUN_ID` | UUID của DriftRun; nếu không đặt sẽ dùng `JOB_ID` làm Redis log key |
| `TENANT_ID` | Tenant sở hữu model |
| `PROJECT_ID` | UUID của model project cần phân tích |
| `MODEL_VERSION_ID` | UUID của model version bất biến cần phân tích |
| `MODEL_NAME` | Tên model (dùng để query production logs) |
| `MODEL_URI` | URI của model (tham khảo) |
| `REFERENCE_DATA_URL` | Presigned URL tải Reference Data từ S3 |
| `DRIFT_THRESHOLD` | Ngưỡng drift để kết luận `drifted` (mặc định: `0.6`) |
| `HTML_S3_URI` | S3 URI để upload HTML report |
| `REPORT_JSON_S3_URI` | S3 URI để upload JSON report |
| `SUMMARY_JSON_S3_URI` | S3 URI để upload JSON summary |
| `CONTROL_PLANE_WEBHOOK_URL` | URL gửi kết quả về Control Plane |
| `REDIS_URL` | Redis database dùng để stream runtime log (TTL 1 giờ) |
| `DB_HOST_RO`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | PostgreSQL (Read-Only) |
| `AWS_BUCKET_NAME`, `AWS_DEFAULT_REGION` | S3 config |

---

## Chú ý

Container này được thiết kế chạy **một lần** (Job, không phải Deployment). Sau khi phân tích xong và gửi webhook, container thoát. Argo Workflows quản lý vòng đời và retry nếu fail.
