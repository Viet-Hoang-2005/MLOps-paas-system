from django.conf import settings

from infrastructure.http import HttpClient


class PrometheusClient:
    def __init__(self, base_url=None, http=None):
        self.base_url = (base_url or settings.PROMETHEUS_INTERNAL_URL).rstrip("/")
        self.http = http or HttpClient(timeout=(2, 8))

    @property
    def enabled(self):
        return bool(self.base_url)

    def query(self, expression):
        if not self.enabled:
            return []
        payload = self.http.request(
            "GET",
            f"{self.base_url}/api/v1/query",
            params={"query": expression},
        ).json()
        return payload.get("data", {}).get("result", [])

    def query_range(self, expression, *, start, end, step):
        if not self.enabled:
            return []
        payload = self.http.request(
            "GET",
            f"{self.base_url}/api/v1/query_range",
            params={"query": expression, "start": start, "end": end, "step": step},
        ).json()
        if payload.get("status") != "success":
            raise RuntimeError("Prometheus query failed.")
        return payload.get("data", {}).get("result", [])
