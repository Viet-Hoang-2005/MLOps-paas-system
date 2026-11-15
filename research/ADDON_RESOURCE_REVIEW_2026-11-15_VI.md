# Rà soát resource Argo CD và addons — 15/11/2026

## Kết luận và giới hạn

Đã đọc toàn bộ 19 Application YAML có `spec` trong `k8s/gitops/production/applications/addons`, values Argo CD, cấu hình Traefik bootstrap và resource thực tế của các container đang chạy. Chỉ đọc cluster; chưa sửa manifests hoặc triển khai.

Snapshot khoảng 12:01 giờ Việt Nam: hai worker, mỗi node 2 CPU và khoảng 7,64 GiB allocatable RAM. Master 2 CPU, khoảng 3,75 GiB allocatable RAM, có taint control-plane. Application controller đã OOMKilled, restart 6 lần với limit 512 MiB. Dex dùng khoảng 101 MiB trên limit 128 MiB. Các số `kubectl top` là snapshot lúc cluster chưa hoàn tất bootstrap, không phải peak hay số đo production đầy đủ. Container đang crash có thể không xuất hiện trong top.

Các giá trị dưới đây là baseline đề xuất cho case study tải thấp, không phải sizing đã benchmark. Không suy ra thiếu RAM chỉ từ trạng thái NotReady. External Secrets cert-controller có readiness lỗi nhưng chưa ghi nhận OOM; cần chẩn đoán riêng.

## 1. Argo CD

Resource áp dụng theo container, một replica hiện tại. `100m` CPU = 0,1 core. Mỗi ô RAM ghi request / limit.

| Thành phần | RAM hiện tại | RAM đề xuất | CPU request / limit đề xuất | Đánh giá |
|---|---|---|---|---|
| Application controller | 256Mi / 512Mi | **1Gi / 2Gi** | 250m / 1000m | P0: có bằng chứng OOM. Theo dõi lại peak khi các CRD và addon còn lại được cài |
| Repo server | 256Mi / 1Gi | 512Mi / 2Gi | 100m / 1000m | Có thể tăng RAM trong các tiến trình con Helm/Kustomize; giới hạn số manifest generation đồng thời |
| Dex | 64Mi / 128Mi | 128Mi / 256Mi | 25m / 250m | Đang dùng khoảng 79% memory limit khi tải thấp |
| Redis của Argo CD | 64Mi / 128Mi | 128Mi / 256Mi | 50m / 200m | Cache tăng khi số object/report tăng; độc lập với Redis ứng dụng |
| Server | 128Mi / 256Mi | 128Mi / 512Mi | 50m / 500m | Bổ sung headroom cho API/UI, chưa có OOM |
| ApplicationSet | 64Mi / 128Mi | 64Mi / 256Mi | 30m / 250m | Tải hiện tại thấp; thêm headroom khi sinh nhiều Application |
| Notifications | 64Mi / 128Mi | Giữ | 20m / 100m | Snapshot khoảng 21 MiB, chưa cần tăng |

RAM request đề xuất cho bảy container chính Argo CD tổng 2 GiB. Đây không phải tổng memory peak hay tổng tài nguyên cluster.

Giới hạn `configs.params.reposerver.parallelism.limit` khởi đầu ở 2; key đã được đối chiếu với chart 7.8.23. Có thể giảm `controller.status.processors` xuống 10 và `controller.operation.processors` xuống 5 để bớt burst trong cụm 4 CPU worker. Đây là điều chỉnh concurrency để nghiệm thu, không thay thế việc cấp đủ bộ nhớ. Không tăng timeout hoặc bỏ health gate để che OOM.

## 2. Addons: bảng đề xuất đầy đủ

RAM và CPU đều tính theo container, không phải tổng Pod. Phần chưa chạy chỉ là đánh giá cấu hình và giả định tải thấp; cần render chart đúng phiên bản để kiểm kê replica, sidecar, init và hook trước khi áp dụng.

| Addon / thành phần | RAM hiện tại | RAM đề xuất | CPU request / limit đề xuất | Hành động |
|---|---|---|---|---|
| Argo Events controller | 64Mi / 128Mi | 128Mi / 256Mi | 30m / 500m | Headroom khi số EventSource/Sensor tăng |
| Argo Workflows controller | 128Mi / 512Mi | 256Mi / 512Mi | 50m / 500m | Tăng reservation; giữ limit khi concurrency còn nhỏ |
| Argo Workflows server | 64Mi / 256Mi | Giữ | 30m / 250m | Chưa có dấu hiệu thiếu resource |
| EBS CSI controller, mỗi container | 64Mi / 256Mi | Giữ | 30m / 200m | Live Pod có 5 container: tổng request RAM 320Mi, không phải 64Mi |
| EBS CSI node, mỗi container | 64Mi / 128Mi | Giữ | 20m / 100m | 3 container trên mỗi worker: 192Mi request/node |
| CloudNativePG operator | 128Mi / 256Mi | 128Mi / 512Mi | 50m / 500m | Tăng dư địa khi reconcile DB/backup; không phải resource của PostgreSQL |
| External Secrets controller | 64Mi / 128Mi | 128Mi / 256Mi | 30m / 500m | Ưu tiên thêm headroom cho reconcile |
| External Secrets webhook | 64Mi / 128Mi | Giữ | 20m / 250m | Chưa có OOM; CPU burst cho admission |
| External Secrets cert-controller | 64Mi / 128Mi | Giữ | 20m / 250m | Snapshot 47Mi; readiness lỗi chưa chứng minh thiếu RAM |
| KEDA operator | 64Mi / 256Mi | 128Mi / 256Mi | 30m / 500m | Dự phòng khi scaler và số workload tăng |
| KEDA metrics server | 64Mi / 256Mi | Giữ | 30m / 500m | CPU burst cho truy vấn metrics, RAM hiện tại thấp |
| KEDA webhook | 64Mi / 128Mi | Giữ | 20m / 250m | Giữ RAM, không đánh đồng restart Error với OOM |
| Kyverno admission controller | 128Mi / 256Mi | **256Mi / 1Gi** | 100m / 1000m | Ưu tiên: image verification và policy admission, cần đo cold-cache/registry chậm |
| Kyverno background controller | 64Mi / 128Mi | 128Mi / 256Mi | 25m / 250m | Chưa chạy; cần đo lúc background scan |
| Kyverno reports controller | 64Mi / 128Mi | 128Mi / 512Mi | 25m / 500m | Report/object churn có thể tăng RAM |
| Kyverno cleanup controller | 64Mi / 128Mi | 64Mi / 256Mi | 25m / 250m | Không cần tăng request đồng loạt |
| Prometheus | 512Mi / 1Gi | **1Gi / 2Gi** | 150m / 1000m | Ưu tiên: series/cardinality và query concurrency; chưa đo runtime |
| Grafana | 128Mi / 256Mi | 128Mi / 512Mi | 50m / 500m | Headroom cho dashboard/query, sidecar tính riêng |
| Alertmanager | 64Mi / 128Mi | 64Mi / 256Mi | 25m / 250m | Headroom cho alert grouping |
| Prometheus operator | 128Mi / 256Mi | 128Mi / 512Mi | 50m / 500m | Dự phòng reconcile nhiều monitor/CRD |
| kube-state-metrics | 64Mi / 128Mi | 128Mi / 256Mi | 25m / 250m | Pod/Job và nhãn UUID tăng theo số lần chạy |
| Loki singleBinary | 256Mi / 1Gi | **512Mi / 2Gi** | 100m / 1000m | Ưu tiên: ingest/query/compaction; S3 không loại bỏ nhu cầu RAM |
| Alloy | 128Mi / 384Mi | 128Mi / 512Mi | 50m / 500m | Bổ sung headroom, phải đo khi nhiều log stream |
| Headlamp | 64Mi / 128Mi | 64Mi / 256Mi | 30m / 250m | Chưa khẩn cấp, headroom khi xem nhiều resource |
| Redis operator | 256Mi / 500Mi | Giữ | 100m / 500m | Chưa có lý do tăng; không giảm request chỉ từ snapshot 12Mi |
| Karpenter controller | 128Mi / 512Mi | 256Mi / 512Mi | 50m / 1000m | Dự phòng scheduling burst; theo dõi khi thực sự provision node |
| Kubeflow Trainer manager | 128Mi / 512Mi | 256Mi / 512Mi | 50m / 500m | Theo dõi số TrainJob và reconcile |
| JobSet controller | 128Mi / 512Mi | Giữ | 100m / 500m | Chưa có dữ liệu yêu cầu tăng limit |
| GPU Operator controller | 128Mi / 256Mi | 256Mi / 512Mi | 50m / 500m | Không bao gồm driver/toolkit/DCGM/device plugin |
| NFD master | 64Mi / 128Mi | 64Mi / 256Mi | 20m / 250m | Thêm headroom khi GPU node xuất hiện |
| NFD worker | 64Mi / 128Mi | 64Mi / 256Mi | 20m / 250m | DaemonSet trên node training; không tính như một replica cố định |
| NFD GC | 32Mi / 64Mi | 32Mi / 128Mi | 10m / 100m | Headroom nhỏ, chưa có OOM |
| Karpenter CRDs Application | Không có container | Không áp dụng | Không áp dụng | CRD không có request/limit riêng |
| Training runtimes Application | Không có controller riêng | Không áp dụng | Không áp dụng | TrainJob/Pod được cấp resource theo từng run, không phải addon thường trực |

## 3. Các container không được thể hiện đầy đủ trong override hiện tại

- **Traefik:** live container chưa có request/limit. Đề xuất ban đầu CPU 50m/1000m, RAM 128Mi/512Mi trong HelmChartConfig của Ansible. Phải đo lại khi nhận predict/upload đồng thời; không suy từ idle 18Mi.
- **CoreDNS:** live 100m/70Mi request, memory limit 170Mi, không CPU limit. Có thể giữ cho cụm nhỏ, tăng memory limit lên 256Mi nếu có nhu cầu DNS/cache hoặc quan sát peak; chưa có bằng chứng OOM.
- **metrics-server:** live request 100m/70Mi và không limit. Đề xuất memory limit 256Mi; không nhất thiết thêm CPU limit thấp.
- **local-path-provisioner và ServiceLB:** live không có request/limit. Cần kiểm kê dưới phần K3s system addons, không tăng số học trên chart override. Khởi đầu local-path 10m/32Mi request, 100m/128Mi limit; ServiceLB 5m/8Mi request và 64Mi memory limit mỗi container, chỉ sau khi xác minh workload thực tế. Không ép CPU limit nhỏ nếu làm giảm khả năng xử lý mạng.
- **Monitoring sidecars/exporters:** chưa có override riêng cho node-exporter, Grafana sidecar, config-reloader và các init container. Cần render chart 69.8.2. Baseline đề xuất: node-exporter 20m/32Mi request, 250m/128Mi limit mỗi node; Grafana sidecar 10m/32Mi request, 200m/128Mi limit mỗi container; config-reloader 10m/32Mi request, 100m/128Mi limit. Chưa khẳng định các default của chart là rỗng.
- **GPU operands:** chưa có override rõ ràng cho driver, toolkit, device-plugin, DCGM/exporter, validators và init. Không áp 512Mi controller limit cho các container đó. Render chart v26.3.3 và quan sát trên GPU node trước khi chọn mức mới; giữ default upstream làm nguồn tham chiếu, không ép mọi container về 128Mi. Dành ngân sách riêng trên training node.
- **EBS CSI:** xác nhận multiplier từ Pod thật; ưu tiên container-specific override nếu cần tối ưu, đừng tăng block resource chung rồi vô tình nhân lên 5 lần/controller và 3 lần/node.
- **Loki:** file hiện có ignoreDifferences cho CPU limit của singleBinary. Cần đối chiếu live resource khi triển khai, không mặc định rằng thay CPU limit trong values luôn dẫn tới reconcile như mong muốn.

## 4. Ngân sách cụm và cách nghiệm thu

1. Tổng allocatable worker hiện khoảng 4 CPU / 15,3 GiB. CPU limit có thể vượt tổng core do chia sẻ, nhưng CPU request phải schedulable. Memory request thấp không khiến container được bảo đảm dùng cả limit khi node chịu áp lực. Nâng request phù hợp với mức steady-state, giữ headroom cho peak và OS/K3s.
2. Chưa thể kết luận tổng request bằng cách cộng một lần mỗi block YAML: phải render đúng chart version, tính replicas/DaemonSet/sidecar và effective init requests, cộng cả platform data plane, tenant serving và rolling-update surge. Không tính dung lượng PVC `storage` thành RAM.
3. Dành khoảng 20–25% RAM worker làm khoảng dự phòng vận hành là mục tiêu lập ngân sách ban đầu, không phải bảo đảm Kubernetes tự reserve phần đó. Sau đó mới tính DB/Redis/Redpanda/Harbor và API/consumer/serving. Không cấp cả 15,3 GiB cho addon requests.
4. Karpenter NodePool hiện gắn `workload-type=training`, trong khi hầu hết addon chọn `workload-type=worker`. Vì vậy Karpenter hiện không tự cứu các addon Pending vì thiếu static-worker capacity. Không dựa vào autoscaling training để bù thiếu tài nguyên nền tảng.
5. Hai worker chưa chứng minh khả năng chịu mất một node. Nếu cần N+1/HA hoặc tải thường xuyên cao, phải thêm/nâng static worker và kiểm tra anti-affinity/storage, không chỉ nâng limit. Hiện chỉ cần sửa P0 trước, tránh nâng mọi request cùng lúc làm workload khác Pending.
6. P0: controller OOM và Dex headroom. P1: repo-server, Kyverno, Prometheus, Loki, Traefik. P2: headroom controller nhỏ theo bảng và bổ sung container còn thiếu sau Helm render.
7. Theo dõi ít nhất 24–72 giờ có full sync, cold-cache Helm/Kustomize, đồng thời Build/Deploy/Predict/drift, log query/compaction và một Training run. Đây là cửa sổ quan sát ban đầu, không bảo đảm bắt hết peak dài hạn.
8. Tính working-set p95/p99 theo container, kiểm tra RSS/cgroup usage và memory limit, restart/OOM, node MemoryPressure, CPU throttling và Pending/FailedScheduling. Working set không phản ánh toàn bộ memory charge; không sizing chỉ từ một ảnh `kubectl top`.
9. Khởi đầu cảnh báo sử dụng memory limit >80% kéo dài 10 phút, cảnh báo gần 90% và bất kỳ OOM/restart bất thường nào. Mức cảnh báo cần tránh gây nhiễu cho cache có thể reclaim. Dựa vào quan sát để điều chỉnh request và limit, không tự động tăng RAM cho readiness lỗi không liên quan.
10. Values Argo CD dùng chung cho Ansible bootstrap và GitOps; phải giữ nhất quán để self-heal không trả lại limit cũ. Báo cáo này chưa thực hiện patch, Helm upgrade, sync hoặc apply lên cluster.

## Áp dụng baseline

Các mức xác định trong bảng Argo CD/addons đã được đưa vào Helm values, cùng resource của Traefik và monitoring sidecars/exporters. Các thành phần ghi “giữ” không thay đổi. GPU operands giữ default upstream; CoreDNS giữ hiện trạng. Các gợi ý có điều kiện cho K3s metrics-server/local-path/ServiceLB chưa được biến thành patch trên workload do K3s quản lý, để tránh cấu hình bị controller ghi đè hoặc thêm một cơ chế ownership khác trong đợt sửa Helm values này. Chúng cần phương án cấu hình bền vững riêng trước khi áp dụng.

Kiểm tra trước rollout: render Helm theo đúng version; 61 container templates có request không vượt limit; 47 manifest validation tests đạt. `configs.params.reposerver.parallelism.limit` là key chart thực tế. Resource bổ sung cho Prometheus/Alertmanager được kiểm tra trên CR của operator; resource sidecar/node-exporter được kiểm tra trên Pod template đã render. Không thay đổi quota hoặc resource tenant job.

## Nguồn tham chiếu

- Repo: `k8s/argocd/values.yaml`, toàn bộ `k8s/gitops/production/applications/addons/*.yaml`, `ansible/roles/k3s_master/templates/traefik-config.yaml.j2`, `k8s/cluster/capacity/karpenter/nodepools.yaml`.
- Quan sát chỉ đọc: Pod specs/containerStatuses, node allocatable, `kubectl top` trên Master và AWS cluster ngày 15/11/2026.
- Kubernetes resource requests/limits: https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/
- Argo CD 2.14 scaling/concurrency: https://argo-cd.readthedocs.io/en/release-2.14/operator-manual/high_availability/
- Prometheus metric cardinality: https://prometheus.io/docs/practices/instrumentation/
