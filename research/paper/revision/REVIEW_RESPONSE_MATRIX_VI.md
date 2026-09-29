# CSoNet: thay đổi đã làm và những phần còn thiếu

Ngày: 27/09/2026. Đây là bảng nội bộ để nhóm/thầy kiểm tra, chưa gửi BTC. Vị trí trỏ theo section để không sai khi PDF đổi trang. Bản sửa giữ title/authors, chuyển bằng chứng chính từ challenger recovery cũ sang thực nghiệm fixed-model có pool tách biệt. Số liệu cơ sở không bị ghi đè.

| Reviewer / vấn đề | Thay đổi thực tế | Vị trí | Trạng thái và giới hạn |
|---|---|---|---|
| R1: novelty của tích hợp còn hạn chế | Nêu rõ contribution là thiết kế quản lý evidence/review và protocol kiểm nghiệm, không phải detector/classifier mới | Abstract, §§1,3,6 | **Làm rõ**, không chứng minh novelty mạnh hay tính đầu tiên |
| R1: cần insight có thể khái quát | Tách distribution alert khỏi labeled performance; minh họa cả drift không degradation và degradation với ít alerts | §§3,5–6 | **Có bằng chứng trong phạm vi kiểm soát**; chưa chứng minh ngoài dataset/model này |
| R1: so với lifecycle/retraining khác | Bỏ recovery/challenger làm evidence chính; giữ model cố định và giới hạn claim | §§1,4–7 | **Chưa có comparison**, công bố hạn chế |
| R1: natural/temporal drift | Công bố nguồn đã tiền xử lý và thiếu time/capture metadata | §§4.1,6 | **Chưa làm**, không dùng nhãn temporal cho shuffled windows |
| R1: threshold sensitivity | 4 ngưỡng × 2 kích thước; BH vs uncorrected; S0 controls | §§4.3,5.2, Table 3 | **Đã làm offline**; ít shifted windows, không chọn threshold production |
| R1: tăng model/tenant/concurrency | Ghi rõ single-model experiment và bounded replay cũ | §§1,5.3,6 | **Chưa chạy sweep**, không claim scalability |
| R2: provenance thiếu | Thêm Kaggle chain, local checksum/split/exclusion manifests và cảnh báo upstream selection | §4.1, artifact | **Một phần**; thiếu acquisition có version xác minh đầy đủ từ raw |
| R2: reuse benign reference/evaluation | Chia lại 4 pool; exact feature-vector dedup, loại conflicting-label groups; 6 cặp overlap bằng 0 | §§4.1–4.2 | **Đã sửa exact overlap trong thí nghiệm mới**, không chứng minh session independence |
| R2: near-perfect challenger không thuyết phục | Loại bảng challenger khỏi bản sửa; giải thích baseline known-family separability và mixture effect | §§4.2,5.1,6 | **Đã đổi evidence/diễn giải**; upstream bias còn |
| R2: replay ngắn/4 HTTP 502 không đủ | Giữ số liệu và lỗi, ghi chưa chạy lại/chưa xác định nguyên nhân; bỏ claim hiệu năng quy mô lớn | §5.3 | **Thu hẹp claim**, chưa có benchmark mới |
| R2: reproducible artifact | Scripts, config, environment, checksums, saved model/window membership, verifier; tài sản LaTeX được tạo từ CSV | §4.3, artifact README | **Tái tính local được**; external reproduction cần đúng CSV nguồn |
| R2: security uploaded model | Phân biệt ownership checks với sandbox, nêu code-execution threats và controls cần có | §6 | **Phân tích giới hạn**, chưa có adversarial/isolation test |
| R2: ablation/promotion/rollback | Nêu drift không tự cho phép cập nhật; các gate và ablation chưa được đánh giá | §§3,6 | **Chưa có thực nghiệm**, không claim policy tốt hơn |
| R2: citation integrity | Sửa 3 lỗi tác giả; ghi article/version; thêm BH; đối chiếu 17 tài liệu giữ lại với claim cụ thể | Related Work, References, citation audit | **Đã sửa lỗi xác minh được**; trigger reviewer chưa rõ, không tự tuyên bố giải quyết hết |

## Kiểm tra sâu bổ sung trước khi chốt bản sửa

Chẩn đoán ngày 27/09 trên model đã khóa cho thấy recall DDoS gần 1, PortScan/WebAttacks gần 0; aggregate S2 recall là hỗn hợp theo tỷ trọng family, không phải bằng chứng loss of knowledge theo thời gian. Bản sửa ghi rõ công thức và kết quả hậu nghiệm; không tính chúng là tập kiểm thử mới.

Code service Evidently dùng preset, còn runner dùng KS+BH riêng. Bản sửa không gán các alert count offline cho detector đã deploy. Chưa có end-to-end parity test.

## Việc nhóm cần chốt trước nộp

1. Đọc chéo và thống nhất contribution/diễn giải của bản sửa; giữ case study NIDS duy nhất.
2. Cung cấp cách lấy đúng `reference_data.csv` có version và checksum, kiểm tra quyền chia sẻ dữ liệu; một thành viên khác chạy lại từ hướng dẫn.
3. Nếu môi trường sẵn, kiểm tra tích hợp stable/shift qua monitor thật. Không chờ một deployment lớn để hoàn tất sửa paper; giữ limitation nếu chưa có kết quả.
4. Xác nhận thông tin tác giả/corresponding author, biểu mẫu, đăng ký và yêu cầu cổng nộp. Xin clarification cho citation trigger nếu cần; chưa gửi bất kỳ email nào từ task này.

Theo [hướng dẫn camera-ready](https://csonet-conf.github.io/csonet26/index.php/camera-ready/index.html), short paper 8 trang, có thể mua tối đa 2 trang thêm; hạn 30/09/2026; nộp PDF kèm source. Bản hiện tại nhắm 8 trang, không thay lề hoặc cỡ chữ để ép trang. Không mặc định thời điểm/múi giờ deadline khi cổng chưa ghi rõ.
