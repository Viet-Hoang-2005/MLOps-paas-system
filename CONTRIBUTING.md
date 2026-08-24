# Hướng dẫn Đóng góp (Contributing Guide)

Tài liệu này cung cấp các nguyên tắc và quy trình để tham gia đóng góp mã nguồn vào dự án **MLOps PaaS System**. Đọc kỹ trước khi tạo Pull Request.

---

## 🚀 Bắt đầu Đóng góp (Getting Started)

```bash
# 1. Fork repository và clone về máy local
git clone https://github.com/<your-username>/mlops-paas-system.git
cd mlops-paas-system

# 2. Tạo branch mới từ main (xem quy tắc đặt tên branch bên dưới)
git checkout -b feature/add-locust-stress-test

# 3. Thực hiện thay đổi và chạy kiểm thử
# (xem phần Testing bên dưới)

# 4. Stage và commit (xem quy tắc commit message bên dưới)
git add .
git commit -m "feat(monitoring): add locust stress test script for drift simulation"

# 5. Push branch lên remote
git push -u origin feature/add-locust-stress-test

# 6. Tạo Pull Request trên GitHub và điền đầy đủ PR template
```

---

## 🌿 Quy tắc Đặt tên Branch (Branch Naming Convention)

Tên branch **phải viết bằng tiếng Anh**, dùng dấu gạch ngang `-` để phân cách từ, theo cú pháp:

```
<type>/<short-kebab-case-description>
```

### Các loại prefix hợp lệ

| Prefix      | Dùng khi nào                            | Ví dụ                                 |
| ----------- | --------------------------------------- | ------------------------------------- |
| `feat/`     | Thêm tính năng mới                      | `feature/cloudnativepg-ha-setup`      |
| `fix/`      | Sửa bug                                 | `fix/postgres-connection-timeout`     |
| `docs/`     | Cập nhật tài liệu                       | `docs/update-architecture-diagram`    |
| `refactor/` | Cải thiện code, không thay đổi behavior | `refactor/db-manager-dual-endpoint`   |
| `test/`     | Thêm hoặc sửa test                      | `test/locust-nids-traffic-simulation` |
| `chore/`    | Công việc bảo trì, upgrade thư viện     | `chore/upgrade-evidently-to-0.5`      |
| `hotfix/`   | Vá lỗi khẩn cấp trên production         | `hotfix/init-container-s3-path`       |

### ✅ Ví dụ đúng

```
feature/add-health-check-endpoint
fix/label-classes-json-path
docs/update-k8s-manifests-readme
chore/update-requirements-sqlalchemy
```

### ❌ Ví dụ sai

```
feature/ThêmTínhNăng        -> Không dùng tiếng Việt
new-feature                 -> Thiếu prefix
Feature/AddEndpoint         -> Không viết hoa prefix
fix_postgres_bug            -> Dùng underscore thay vì hyphen
```

---

## 📝 Quy tắc Commit Message (Conventional Commits)

Commit message **phải viết bằng tiếng Anh**, tuân thủ chuẩn [Conventional Commits](https://www.conventionalcommits.org/), theo cú pháp:

```
<type>(<scope>): <short imperative description>

[optional body]

[optional footer: Closes #issue]
```

### Các type hợp lệ

| Type       | Ý nghĩa                                                 |
| ---------- | ------------------------------------------------------- |
| `feat`     | Thêm tính năng mới                                      |
| `fix`      | Sửa bug                                                 |
| `docs`     | Cập nhật tài liệu                                       |
| `refactor` | Tái cấu trúc code (không thêm tính năng, không sửa bug) |
| `test`     | Thêm hoặc chỉnh sửa test                                |
| `chore`    | Bảo trì: update dependencies, config, CI scripts        |
| `perf`     | Cải thiện hiệu năng                                     |
| `cicd`     | Thay đổi CI/CD workflows                                |

### Scope gợi ý cho dự án này

`web` · `control-plane` · `model-server` · `terraform` · `ansible` · `k8s` · `cicd` · `skills`

### ✅ Ví dụ đúng

```
feat(api): add GET / health check endpoint returning model version

- Returns {"status": "healthy", "model_version": "v1"}
- Used by ALB readinessProbe and Kubernetes liveness check
```

```
fix(k8s): correct init container file path from .pkl to .json

The label encoder was exported as label_classes_v1.json by train.py
but api-deployment.yaml was pulling label_nids_encoder_v1.pkl.
```

```
refactor(db): split db_manager into rw and ro connection pools

Support CloudNativePG dual-endpoint architecture:
- engine_rw -> mlops-paas-postgres-rw (Primary, for INSERT)
- engine_ro -> mlops-paas-postgres-ro (Standby, for SELECT)
```

```
ci(pipeline): fix kaggle kernel slug to match kernel-metadata.json
```

### ❌ Ví dụ sai

```
fix bug                         -> Không có type, không có mô tả rõ
Sửa lỗi kết nối PostgreSQL      -> Không viết bằng tiếng Anh
feat: added some new stuff      -> Mô tả quá mơ hồ
FEAT(API): Add endpoint         -> Không viết hoa type và scope
```

---

## ⭐ Checklist trước khi tạo Pull Request

Đảm bảo tất cả các mục sau đây trước khi submit PR:

- [ ] Code tuân thủ chuẩn **PEP 8** (có thể dùng `flake8` để kiểm tra)
- [ ] Không có lỗi syntax: `flake8 api/src/ monitoring/ --select=E9,F63,F7,F82`
- [ ] Branch đã được rebase/merge từ `main` mới nhất
- [ ] Docker image build được thành công (test local)
- [ ] API khởi động và `/` trả về `{"status": "healthy"}` thành công
- [ ] Không hardcode credentials, passwords, hay API keys trong code
- [ ] Đã cập nhật tài liệu liên quan (`ARCHITECTURE.md`, `INSTALL.md`, ...) nếu có thay đổi kiến trúc
- [ ] Điền đầy đủ PR Template [.github/PULL_REQUEST_TEMPLATE.md](.github/PULL_REQUEST_TEMPLATE.md)

---

## ⚠️ Báo lỗi & Yêu cầu Tính năng (Issues)

Sử dụng GitHub Issue Templates có sẵn:

- **Báo cáo Bug:** [.github/ISSUE_TEMPLATE/ISSUE_BUG.md](.github/ISSUE_TEMPLATE/ISSUE_BUG.md)
- **Yêu cầu tính năng:** [.github/ISSUE_TEMPLATE/ISSUE_FEATURE.md](.github/ISSUE_TEMPLATE/ISSUE_FEATURE.md)

Khi báo bug, vui lòng cung cấp:

1. Các bước để tái hiện lỗi
2. Log đầy đủ (`kubectl logs <pod-name>` hoặc terminal output)
3. Phiên bản hệ thống (K3s version, Python version, OS)

---

## 💬 Liên hệ & Trao đổi

| Kênh            | Địa chỉ                                                                                                            |
| --------------- | ------------------------------------------------------------------------------------------------------------------ |
| Email tác giả 1 | <23520541@gm.uit.edu.vn>                                                                                             |
| Email tác giả 2 | <23521412@gm.uit.edu.vn>                                                                                             |
| GitHub Issues   | [github.com/Viet-Hoang-2005/MLOps-paas-system/issues](https://github.com/Viet-Hoang-2005/MLOps-paas-system/issues) |
