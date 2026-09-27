# Bàn giao thực nghiệm CSoNet: drift và chất lượng NIDS

**Cập nhật 27/09/2026.** Bản runbook benchmark hạ tầng trước được thay bằng phạm vi người dùng đã chốt: kiểm chứng data drift có đi kèm suy giảm chất lượng model hay không.

## Kế hoạch chính

Đọc và thực hiện theo [csonet_2026_one_week_drift_plan_vi.md](../../../docs/paper/csonet_2026_one_week_drift_plan_vi.md). Đây là bản kế hoạch chính đã cập nhật từ kết quả offline hiện có; không duy trì thêm một ma trận benchmark khác tại file này.

Để lấy code và xuất bộ dữ liệu chạy thực tế, dùng [hướng dẫn bàn giao qua Git](../experiments/drift_only/HANDOFF_VI.md). Script xuất đã kiểm tra offline; bạn có cùng dataset thì không cần nhận ZIP riêng.

| Cần làm | Đọc mục trong kế hoạch chính |
|---|---|
| Hiểu review, phạm vi đã đáp ứng và còn thiếu | Mục 1–3 |
| Khóa model/reference/data/seeds và phân biệt các thresholds | Mục 4 |
| Biết chính xác S0/S1/S2 thay đổi dữ liệu gì | Mục 5 |
| Thu metric, tính suy giảm và phân tích sensitivity | Mục 6–8 |
| Replay qua hệ thống, audit đúng window và so với offline | Mục 9 |
| Phân tích lỗi theo từng họ attack | Mục 10 |
| Chuẩn bị bảng/hình và diễn giải kết quả cho paper | Mục 11–12 |
| Phân công, mốc 27–30/09 và artifact bàn giao | Mục 13–15 |

## Giao việc ngay

- **Người phụ trách ML/paper:** giữ frozen artifact, xuất inputs/sidecar/expected outputs theo membership, ghép bảng drift–quality, phân tích recall/FN theo family và viết Results/Discussion.
- **Người phụ trách hệ thống:** replay S0, S1_a85, S2_r50, S2_r100 ở n=1000; pilot seed 42 trước, sau đó mở rộng seeds 123 và 456 nếu audit đạt. Tổng đầy đủ là 12 cửa sổ/12000 inference hợp lệ, cùng một model và reference.
- **Người kiểm tra:** đối chiếu hashes, membership, confusion matrix, family counts, report và các số liệu đưa vào manuscript.

Phần replay chưa có kết quả mới. Không dùng số liệu offline như số liệu đo từ service. Prometheus/Grafana hỗ trợ chẩn đoán luồng chạy; bằng chứng model quality phải đến từ dự đoán ghép với nhãn thật. Chi tiết tiêu chí hoàn thành nằm ở mục 9 của kế hoạch chính.

File PDF cùng tên nếu còn trong thư mục là bản xuất cũ, **không đồng bộ với lần cập nhật Markdown này**. Dùng kế hoạch Markdown chính ở liên kết trên để giao việc.
