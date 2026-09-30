# ARS-Codex review — CSoNet 2026 camera-ready (29/09/2026)

**Phạm vi:** bản LaTeX LNCS hiện tại, hai review trong thư chấp nhận, thí nghiệm offline đã khóa (run_20260926), báo cáo pilot dịch vụ ngày 29/09, và các reference còn được trích. Đây là review có đối chiếu nguồn và số liệu, không phải chứng nhận rằng mọi yêu cầu của reviewer đã hoàn thành.

## Kết luận biên tập

Bản thảo phù hợp hơn với **short paper mô tả prototype và một case study NIDS có kiểm soát**. Luận điểm được bảo vệ tốt nhất là: tỷ lệ feature drift không suy ra mức giảm chất lượng của một mô hình cố định, nên evidence phân phối và evidence hiệu năng có nhãn phải lưu/tư duy riêng trước quyết định lifecycle. Không gọi S2 là concept drift theo thời gian; đó là thay thành phần attack family trong cùng derivative dataset.

**Điểm mạnh:** nguồn dữ liệu và giới hạn upstream được nói rõ; train/reference/evaluation tách theo vector chính xác; có S0 control, 120 windows offline, kiểm tra threshold và kích thước window; bảng kết quả nhất quán với CSV; pilot bốn cửa sổ nối được inference → persistence → Evidently và làm rõ sự khác biệt KS/BH offline so với Evidently live.

**Giới hạn còn trọng yếu:** chưa có natural/temporal drift, đối chứng retraining/lifecycle, ablation, load sweep nhiều model/tenant/concurrency, hay kiểm thử sandbox model upload. Live pilot chỉ một seed cho mỗi kịch bản, một artifact/reference; S0 phải phục hồi nhãn dự đoán class 0 từ UI sau lỗi consumer, S1 có 42 request HTTP 502/503 trong lúc node/worker gián đoạn. Không dùng pilot để tuyên bố độ sẵn sàng hoặc khả năng mở rộng. Các cửa sổ cùng pool nên độ lệch chuẩn không đại diện cho nhiều capture độc lập.

## Những sửa đổi đã đưa vào LaTeX

- Viết rõ policy **đề xuất**: drift alert → kiểm tra, suy giảm có nhãn phải được xem xét ngay cả khi không có alert; chỉ cân nhắc huấn luyện với dữ liệu gắn nhãn đại diện, và promotion cần challenger vượt gate chất lượng/vận hành cùng duyệt của người. Paper ghi rõ policy chưa được kiểm nghiệm.
- Giữ phần service replay ngắn và tách khỏi bảng KS/BH; nêu việc audit S0 từ UI và 42 lỗi S1 theo đúng pilot report.
- Bỏ link GitHub khỏi bản thảo vì repository dự kiến chuyển sang private. Vẫn ghi rõ rằng việc tái lập cần đúng CSV đầu vào theo checksum và quy trình lấy đúng version chưa hoàn tất; raw pilot logs ở thư mục tmp chưa được phát hành.
- Sửa cách gọi verifier thành “separate verifier” để tránh hàm ý có bên độc lập xác nhận.
- Rút ba nguồn ít trực tiếp với câu hỏi nghiên cứu: bài dự báo thị trường điện, bài tổng quan data quality, và preprint so sánh workflow frameworks. Giữ 13 nguồn được trích; bổ sung DOI xác minh cho Sommer–Paxson. Sau khi thêm lời cảm ơn, lược thêm nghiên cứu Amershi et al. để giữ giới hạn trang. Không thay số liệu thực nghiệm hay format/lề LNCS.

## Kiểm tra reference

13/13 citation keys có bibitem; không có reference chưa trích hoặc citation thiếu định nghĩa; 8 mục có DOI. Metadata/claim của các mục giữ lại đã đối chiếu với nguồn tác giả, nhà xuất bản, hội nghị hoặc arXiv version trong [citation audit](CITATION_AUDIT_2026-09-27.md). DOI mới của Sommer–Paxson được đối chiếu với [dblp](https://dblp.org/rec/conf/sp/SommerP10.html), còn [bản tác giả](https://www.icir.org/robin/papers/oakland10-ml.pdf) xác nhận nội dung tương ứng. Nguồn DOI IEEE trực tiếp không truy cập được trong lần kiểm tra này. Reviewer 2 không nêu citation cụ thể gây “citation-integrity trigger”, nên **không thể kết luận trigger đã được giải quyết**.

## Quyết định cần nhóm chốt trước 30/09

1. Một tác giả kiểm tra danh tính, thứ tự tác giả, email, lời cảm ơn tài trợ, disclosure và đối chiếu PDF với bản đã accepted; riêng disclosure “no competing interests” là nội dung nhóm đã xác nhận.
2. Cung cấp/quyết định cách phát hành chính xác data/reference_data.csv SHA-256 0728925d293f433a3f7bce4509c00e1648906c59c59d8e63663e1622a226ef6c, cùng version/license của Kaggle derivative. Repo hiện có script/manifest nhưng người ngoài chưa tự lấy được đúng byte dữ liệu.
3. Kiểm tra source ZIP/PDF cuối và nộp qua cổng hội nghị. Nếu có thể, hỏi BTC về citation trigger; không giả định đã được chấp thuận vì citation keys và DOI hợp lệ.
4. Giữ các benchmark tự nhiên/temporal, retraining đối chứng và multi-tenant load sweep ở mục limitation/future work nếu không có số liệu thật trước hạn.

Đã bổ sung nguyên văn lời cảm ơn của thầy trong credits trước Disclosure of Interests, theo template LNCS. Bản trước khi bỏ URL đã chạy hai lượt pdflatex với llncs.cls v2.24 và ra **8 trang** như giới hạn short paper trên [trang camera-ready chính thức](https://csonet-conf.github.io/csonet26/index.php/camera-ready/index.html). Bản nguồn mới đã bỏ URL GitHub; editor tự cập nhật PDF 8 trang trên đĩa, và trang 5 đã được kiểm tra trực quan để xác nhận URL biến mất. Lệnh compile tích hợp gọi riêng vẫn báo lỗi môi trường “Unable to find standard directories for platform”, nên không có xác nhận thành công từ lệnh đó. Không có submission ra ngoài trong lượt này.