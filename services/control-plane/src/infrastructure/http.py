import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class HttpClient:
    def __init__(self, timeout=(3.05, 15), session=None):
        self.timeout = timeout
        self.session = session or requests.Session()
        retry = Retry(
            total=3,
            connect=3,
            read=2,
            backoff_factor=0.5,
            status_forcelist=(429, 502, 503, 504),
            allowed_methods=("GET", "HEAD", "PUT", "DELETE", "OPTIONS"),
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def request(self, method, url, **kwargs):
        kwargs.setdefault("timeout", self.timeout)
        response = self.session.request(method, url, **kwargs)
        response.raise_for_status()
        return response
