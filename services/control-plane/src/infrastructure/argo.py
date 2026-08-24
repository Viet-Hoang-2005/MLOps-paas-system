from common.api.exceptions import ServiceUnavailable
from django.conf import settings

from infrastructure.http import HttpClient


class ArgoWebhookClient:
    def __init__(self, http=None):
        self.http = http or HttpClient()

    def trigger(self, url, payload, headers=None):
        if not url:
            raise ServiceUnavailable("Argo webhook URL is not configured.")
        token = str(settings.ARGO_EVENTS_WEBHOOK_TOKEN).strip()
        if not token:
            raise ServiceUnavailable("Argo Events webhook authentication is not configured.")
        request_headers = dict(headers or {})
        request_headers["Authorization"] = f"Bearer {token}"
        return self.http.request("POST", url, json=payload, headers=request_headers).json()
