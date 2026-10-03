export const monitoringVi = {
  unsaved: "Thay đổi chưa lưu",
  leaveHint: "Rời trang và bỏ cấu hình chưa lưu?",
  selectProject: "Chọn Model Project đang Running",
  referenceSnapshotHint:
    "CSV được đóng băng riêng cho monitor, không sửa Preview hoặc phiên bản đã đăng ký.",
  usingVersionReference: "Dùng snapshot CSV tham chiếu của phiên bản Running.",
  runningDriftOnly:
    "Chỉ giám sát Data drift. Monitor lưu lịch sử theo phiên bản; tạo monitor mới sau khi đổi Running.",
  active: "Đang hoạt động",
  archived: "Lưu lịch sử",
  currentStatus: "Phiên bản Running · Data drift",
  noCurrentResult: "Chưa có kết quả drift hoàn tất cho phiên bản Running.",
  driftDetected: "Phát hiện drift",
  healthy: "Không phát hiện drift",
  createMonitoring: "Tạo Drift Monitoring",
} as const;
