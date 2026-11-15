"""Build/register/deploy a frozen model through the ordinary platform APIs."""
import argparse
import hashlib
import json
import time
from pathlib import Path

import httpx
from bridge import Api, Bridge


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', required=True)
    parser.add_argument('--key', required=True)
    parser.add_argument('--owner', required=True)
    parser.add_argument('--api', required=True)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--replacement-artifact', type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    state_path = args.output / 'preparation.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    api = Api(Bridge(args.host, args.key, args.owner), args.api)
    if state.get('build_id') and args.replacement_artifact:
        previous = api.call('GET', f"/builds/{state['build_id']}/")
        if previous['status'] == 'failed':
            artifact = args.replacement_artifact
            data = artifact.read_bytes()
            upload = api.call('POST', f"/models/{state['project_id']}/preview/upload-urls/", json={
                'flavor': 'xgboost', 'artifact_format': 'mlflow_zip',
                'files': [dict(kind='source_artifact', filename=artifact.name, size_bytes=len(data), content_type='application/zip')],
            })['files'][0]
            response = httpx.put(upload['upload_url'], content=data, headers={'Content-Type': upload['content_type']}, timeout=120)
            if response.status_code not in (200, 201, 204):
                raise RuntimeError('Replacement artifact upload failed')
            preview = api.call('GET', f"/models/{state['project_id']}/preview/")
            preview = api.call('PATCH', f"/models/{state['project_id']}/preview/", json={
                'revision': preview['revision'], 'artifact_format': 'mlflow_zip',
                'assets': [dict(kind='source_artifact', name=artifact.name, s3_uri=upload['s3_uri'],
                                checksum=hashlib.sha256(data).hexdigest())],
            })
            state.setdefault('previous_failed_builds', []).append(state.pop('build_id'))
            state['preview_revision'] = preview['revision']
            save(state_path, state)
    if 'project_id' not in state:
        name = 'csonet-timing-' + time.strftime('%Y%m%d-%H%M%S', time.gmtime())
        sources = {
            'source_artifact': args.bundle / 'model/mlflow.zip',
            'reference_data': args.bundle / 'reference/features.csv',
        }
        specs = [dict(kind=kind, filename=path.name, size_bytes=path.stat().st_size,
                      content_type='text/csv' if kind == 'reference_data' else 'application/zip')
                 for kind, path in sources.items()]
        upload = api.call('POST', '/models/preview/upload-urls/', json={
            'name': name, 'flavor': 'xgboost', 'artifact_format': 'mlflow_zip', 'files': specs,
        })
        assets = []
        for item in upload['files']:
            data = sources[item['kind']].read_bytes()
            response = httpx.put(item['upload_url'], content=data,
                                 headers={'Content-Type': item['content_type']}, timeout=120)
            if response.status_code not in (200, 201, 204):
                raise RuntimeError(f"Artifact upload failed with HTTP {response.status_code}")
            assets.append(dict(kind=item['kind'], name=item['filename'], s3_uri=item['s3_uri'],
                               checksum=hashlib.sha256(data).hexdigest()))
        requirements = (args.bundle / 'model/mlflow/requirements.txt').read_text()
        project = api.call('POST', '/models/', json={
            'project_id': upload['project_id'], 'name': name, 'description': 'Isolated CSoNet production timing',
            'access_mode': 'private', 'flavor': 'xgboost', 'artifact_format': 'mlflow_zip',
            'requirements_text': requirements, 'assets': assets,
        })
        state.update(project_id=project['id'], project_name=name, preview_revision=project['preview_revision'])
        save(state_path, state)
        print('Created benchmark project', project['id'], flush=True)
    if 'build_id' not in state:
        build = api.call('POST', f"/models/{state['project_id']}/builds/",
                         json={'revision': state['preview_revision']})
        state['build_id'] = build['id']
        save(state_path, state)
    deadline = time.monotonic() + 1800
    while True:
        build = api.call('GET', f"/builds/{state['build_id']}/")
        status = build['status']
        print('Build status', status, flush=True)
        if status == 'ready':
            state['image_digest'] = build['image_digest']
            break
        if status in ('failed', 'cancelled') or time.monotonic() > deadline:
            save(args.output / 'build-failure.json', {'status': status, 'error': build.get('error_message', '')})
            raise RuntimeError('Build failed or exceeded preparation deadline')
        time.sleep(15)
    if not build.get('version_id'):
        api.call('POST', f"/builds/{state['build_id']}/register/", json={})
        for _ in range(60):
            build = api.call('GET', f"/builds/{state['build_id']}/")
            if build.get('version_id'):
                break
            if build['registration_status'] == 'failed':
                raise RuntimeError('Version registration failed')
            time.sleep(5)
    state['version_id'] = build['version_id']
    save(state_path, state)
    if 'deployment_id' not in state:
        deployment = api.call('POST', '/deployments/', json={'build': state['build_id']})
        state['deployment_id'] = deployment['id']
        save(state_path, state)
    for _ in range(120):
        deployment = api.call('GET', f"/deployments/{state['deployment_id']}/")
        print('Deployment status', deployment['status'], flush=True)
        if deployment['status'] == 'succeeded':
            project = api.call('GET', f"/models/{state['project_id']}/")
            state['predict_url'] = project['active_endpoint']['url']
            state['health_url'] = project['active_endpoint']['health_url']
            save(state_path, state)
            print('Benchmark model ready', state['version_id'], flush=True)
            return
        if deployment['status'] in ('failed', 'cancelled'):
            raise RuntimeError('Deployment failed')
        time.sleep(5)
    raise RuntimeError('Deployment readiness deadline exceeded')


if __name__ == '__main__':
    main()
