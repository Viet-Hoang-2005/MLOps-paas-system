# Environment troubleshooting

1. Reproduce the exact action and capture the first failing request/task.
2. Identify the owning service and inspect only its recent logs.
3. Check configuration presence without printing secret values.
4. Verify DNS/service name, port, network membership, and health endpoint from the caller's network.
5. Check PostgreSQL lifecycle state; do not infer completion only from a running container.
6. Inspect Redis log stream only as transient evidence.
7. Confirm Docker/Argo backend selection and external job/runtime ID.
8. Restart only after identifying a configuration or stale-process cause.
9. Recheck health, task processing, and the user flow.

Common local failures include stale images, Compose service DNS versus localhost confusion, missing Docker socket access, duplicate Celery beat pidfiles, and containers not recreated after environment changes.

Safe restart example: recreate only the affected Compose service, then verify its state and logs. Never use volume deletion as routine troubleshooting.
