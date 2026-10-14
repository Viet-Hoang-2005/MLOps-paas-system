# Detailed breakdown calculation script

workloads = [
    # (Category, Name, Replicas, CPU Req (m), Mem Req (Mi), CPU Lim (m), Mem Lim (Mi), Notes)
    # 1. CORE WORKLOADS (apps/base/)
    ("Workloads", "control-plane-api", 2, 100, 256, 1000, 1024, "Django REST API"),
    ("Workloads", "celery-worker", 2, 100, 256, 1000, 1024, "Celery task workers"),
    ("Workloads", "celery-beat", 1, 50, 128, 250, 256, "Celery beat scheduler"),
    ("Workloads", "celery-health-worker", 1, 100, 256, 500, 1024, "Health check periodic worker"),
    ("Workloads", "consumer", 1, 150, 384, 750, 768, "Redpanda consumer service"),
    ("Workloads", "model-server", 2, 150, 256, 750, 768, "Model serving gateway"),
    ("Workloads", "web", 1, 100, 128, 500, 512, "React/Vite Nginx frontend"),

    # 2. PLATFORM DATA SERVICES
    ("Platform", "cloudnative-pg-instances", 2, 250, 512, 1000, 1024, "PostgreSQL HA (Primary + Replica)"),
    ("Platform", "redis-replication", 2, 125, 576, 1200, 1152, "Redis HA (Master + Replica + Exporter)"),
    ("Platform", "redis-sentinel", 2, 50, 128, 400, 256, "Redis Sentinel (2 on workers, 1 on master)"),
    ("Platform", "redpanda", 1, 200, 1024, 1000, 2048, "Kafka-compatible message queue"),
    ("Platform", "cloudflared", 2, 50, 64, 200, 128, "Cloudflare Tunnel egress"),

    # 3. ADDONS & OPERATORS
    ("Addons", "aws-ebs-csi-controller", 1, 60, 240, 0, 1536, "CSI controller provisioner/attacher/resizer"),
    ("Addons", "aws-ebs-csi-node", 2, 30, 120, 0, 768, "CSI daemonset per worker node"),
    ("Addons", "cloudnative-pg-operator", 1, 100, 128, 500, 512, "CNPG operator manager"),
    ("Addons", "external-secrets-operator", 3, 50, 64, 200, 256, "ESO core + cert-controller + webhook"),
    ("Addons", "redis-operator", 1, 100, 256, 500, 500, "OT-Container-Kit Redis operator"),
    ("Addons", "keda-operator-suite", 3, 125, 300, 3000, 3000, "KEDA operator + metrics + webhook"),
    ("Addons", "argo-workflows-controller", 1, 100, 256, 1000, 1024, "Workflow controller"),
    ("Addons", "argo-workflows-server", 1, 50, 128, 500, 512, "Argo UI & API server"),
    ("Addons", "argo-events-suite", 4, 100, 200, 500, 1000, "EventBus (NATS) + Controller + Sensor"),
    ("Addons", "kyverno-policy-engine", 4, 125, 320, 0, 768, "Kyverno admission, bg, cleanup, reports"),
    ("Addons", "loki", 1, 100, 256, 1000, 1024, "Loki log aggregation"),
    ("Addons", "alloy", 1, 60, 178, 500, 384, "Grafana Alloy collector"),
    ("Addons", "monitoring-prometheus", 1, 300, 800, 1000, 1500, "Prometheus server (active monitoring)"),
    ("Addons", "monitoring-grafana", 1, 100, 200, 500, 512, "Grafana Dashboard"),
    ("Addons", "monitoring-node-exporter", 2, 20, 50, 100, 100, "Prometheus node-exporter DaemonSet"),
    ("Addons", "monitoring-kube-state-metrics", 1, 50, 100, 200, 256, "Cluster state metrics exporter"),
    ("Addons", "monitoring-operator", 1, 50, 100, 200, 256, "Prometheus operator"),
    ("Addons", "headlamp", 1, 50, 128, 250, 256, "Headlamp Web UI"),
    ("Addons", "karpenter-controller", 1, 100, 256, 1000, 1024, "Karpenter autoscaler controller"),
    ("Addons", "kubeflow-training-operator", 1, 100, 200, 500, 512, "Kubeflow training operator"),
    ("Addons", "nfd-suite", 2, 60, 200, 200, 500, "Node Feature Discovery"),
]

total_cpu_req = sum(item[2] * item[3] for item in workloads)
total_mem_req = sum(item[2] * item[4] for item in workloads)
total_cpu_lim = sum(item[2] * item[5] for item in workloads)
total_mem_lim = sum(item[2] * item[6] for item in workloads)

print("="*60)
print(f"TOTAL PODS SCHEDULED: {sum(item[2] for item in workloads)}")
print(f"TOTAL CPU REQUESTS: {total_cpu_req}m ({total_cpu_req/1000.0:.2f} vCPU)")
print(f"TOTAL MEM REQUESTS: {total_mem_req}Mi ({total_mem_req/1024.0:.2f} GiB)")
print(f"TOTAL CPU LIMITS:   {total_cpu_lim}m ({total_cpu_lim/1000.0:.2f} vCPU)")
print(f"TOTAL MEM LIMITS:   {total_mem_lim}Mi ({total_mem_lim/1024.0:.2f} GiB)")
print("="*60)

# Breakdown by Category
for cat in ["Workloads", "Platform", "Addons"]:
    cat_items = [it for it in workloads if it[0] == cat]
    c_req = sum(item[2] * item[3] for item in cat_items)
    m_req = sum(item[2] * item[4] for item in cat_items)
    c_lim = sum(item[2] * item[5] for item in cat_items)
    m_lim = sum(item[2] * item[6] for item in cat_items)
    print(f"\n--- Category: {cat} ({len(cat_items)} components, {sum(item[2] for item in cat_items)} pods) ---")
    print(f"  CPU Request: {c_req}m ({c_req/1000.0:.2f} vCPU), Mem Request: {m_req}Mi ({m_req/1024.0:.2f} GiB)")
    print(f"  CPU Limit:   {c_lim}m ({c_lim/1000.0:.2f} vCPU), Mem Limit:   {m_lim}Mi ({m_lim/1024.0:.2f} GiB)")
    for it in cat_items:
        print(f"    * {it[1]} (x{it[2]}): Req: {it[2]*it[3]}m / {it[2]*it[4]}Mi | Lim: {it[2]*it[5]}m / {it[2]*it[6]}Mi ({it[7]})")
