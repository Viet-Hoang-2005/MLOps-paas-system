"""Scoped SSH/Django access for the isolated conference benchmark."""
import json
import re
import subprocess
from pathlib import Path

def redact(text):
    text = re.sub(r'https?://[^\s<>\"]+',
                  lambda match: match.group().split('?')[0] + '?[redacted]' if '?' in match.group() else match.group(),
                  str(text))
    text = re.sub(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b', '[redacted-key]', text)
    return re.sub(r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', '[redacted-token]', text)


class Bridge:
    def __init__(self, host, key, owner):
        self.host = host
        self.key = str(Path(key).expanduser().resolve())
        self.owner = owner

    def execute(self, code, **parameters):
        parameters['owner'] = self.owner
        program = (
            'import json\n'
            f'P = json.loads({json.dumps(parameters)!r})\n'
            f'try:\n    exec({code!r}, globals())\n'
            '    print("BENCH_JSON=" + json.dumps(result, default=str))\n'
            'except Exception as error:\n'
            '    print("BENCH_ERROR=" + json.dumps({"type": type(error).__name__, '
            '"detail": str(error) if isinstance(error, ValueError) else "Remote operation failed"}))\n'
        )
        command = [
            'ssh', '-i', self.key, '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
            self.host,
            'sudo k3s kubectl exec -i -n mlops-paas-core '
            'deploy/mlops-paas-control-plane -- python manage.py shell',
        ]
        response = subprocess.run(command, input=program, text=True, capture_output=True, timeout=90)
        if response.returncode:
            # Avoid echoing remote environment, traceback locals or credential-bearing URLs.
            raise RuntimeError('Remote Django operation failed. Inspect its operation and scoped state.')
        for line in reversed(response.stdout.splitlines()):
            if line.startswith('BENCH_JSON='):
                return json.loads(line.removeprefix('BENCH_JSON='))
            if line.startswith('BENCH_ERROR='):
                error = json.loads(line.removeprefix('BENCH_ERROR='))
                raise RuntimeError(f"Remote {error['type']}: {error['detail']}")
        raise RuntimeError('Remote operation did not return its structured result')

    def access_token(self):
        return self.execute('''
from django.contrib.auth import get_user_model
from apps.auth.api.serializers import _KeyIdAccessToken
user = get_user_model().objects.get(email=P['owner'], is_active=True)
token = _KeyIdAccessToken.for_user(user)
token['tenant_id'] = user.tenant_id
result = {'access': str(token), 'expires_at': int(token['exp']), 'tenant_id': user.tenant_id}
''')

    def records(self, project_id, version_id):
        return self.execute('''
from apps.catalog.models import ModelProject
from apps.production.models import PredictionRecord
project = ModelProject.objects.get(public_id=P['project_id'], owner__email=P['owner'])
if not project.name.startswith('csonet-timing-'):
    raise ValueError('Project is outside benchmark scope')
rows = PredictionRecord.objects.filter(project=project, model_version__public_id=P['version_id'])
result = list(rows.values('public_id', 'request_id', 'features', 'prediction', 'observed_at', 'created_at'))
''', project_id=project_id, version_id=version_id)

    def cleanup(self, project_id, version_id, ids, request_prefix):
        return self.execute('''
from django.db import transaction
from apps.catalog.models import ModelProject
from apps.production.models import PredictionRecord
with transaction.atomic():
    project = ModelProject.objects.select_for_update().get(public_id=P['project_id'], owner__email=P['owner'])
    if not project.name.startswith('csonet-timing-'):
        raise ValueError('Project is outside benchmark scope')
    rows = PredictionRecord.objects.filter(project=project, model_version__public_id=P['version_id'])
    actual = set(str(value) for value in rows.values_list('public_id', flat=True))
    if actual and actual != set(P['ids']):
        raise ValueError('Unexpected records in benchmark version')
    if rows.exclude(request_id__startswith=P['request_prefix']).exists():
        raise ValueError('Unexpected request prefix in benchmark version')
    count = len(actual)
    if count:
        rows.filter(public_id__in=P['ids']).delete()
    result = {'deleted': count, 'remaining': rows.count(), 'already_clean': count == 0}
''', project_id=project_id, version_id=version_id, ids=ids, request_prefix=request_prefix)


class Api:
    def __init__(self, bridge, base_url):
        import httpx
        self.bridge = bridge
        self.base_url = base_url.rstrip('/')
        self.client = httpx.Client(timeout=60, follow_redirects=False)
        self.token = None

    def headers(self):
        import time
        if self.token is None or self.token['expires_at'] - time.time() < 120:
            self.token = self.bridge.access_token()
        return {'Authorization': 'Bearer ' + self.token['access']}

    def call(self, method, route, **kwargs):
        response = self.client.request(method, self.base_url + route, headers=self.headers(), **kwargs)
        if response.is_error:
            # No response/request headers or presigned URLs enter errors.
            raise RuntimeError(f'{method} {route} returned HTTP {response.status_code}: {redact(response.text[:600])}')
        return response.json()
