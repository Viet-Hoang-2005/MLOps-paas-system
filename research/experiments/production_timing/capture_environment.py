"""Collect image identities and resources without retaining pod environment values."""
import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def remote_json(host, key, command):
    response = subprocess.run(['ssh', '-i', str(key.expanduser()), '-o', 'BatchMode=yes', host,
                               'sudo k3s kubectl ' + command], capture_output=True, text=True, timeout=60)
    if response.returncode:
        raise RuntimeError('Environment inventory command failed')
    return json.loads(response.stdout)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', required=True)
    parser.add_argument('--key', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    nodes = remote_json(args.host, args.key, 'get nodes -o json')
    pods = remote_json(args.host, args.key, 'get pods -A -o json')
    result = {'observed_utc': datetime.now(timezone.utc).isoformat(), 'nodes': [], 'pods': []}
    for node in nodes['items']:
        result['nodes'].append({
            'name': node['metadata']['name'], 'capacity': node['status']['capacity'],
            'allocatable': node['status']['allocatable'], 'node_info': node['status']['nodeInfo'],
            'instance_type': node['metadata']['labels'].get('node.kubernetes.io/instance-type'),
        })
    for pod in pods['items']:
        namespace = pod['metadata']['namespace']
        if namespace not in ('mlops-paas-core', 'mlops-paas-execution', 'mlops-paas-model-runtimes',
                             'mlops-paas-serving', 'mlops-paas-data'):
            continue
        result['pods'].append({
            'name': pod['metadata']['name'], 'namespace': namespace,
            'node': pod['spec'].get('nodeName'), 'phase': pod['status']['phase'],
            'containers': [dict(name=container['name'], image=container['image'], resources=container.get('resources', {}))
                           for container in pod['spec']['containers']],
            'image_ids': [dict(name=container['name'], image_id=container.get('imageID'), restart_count=container['restartCount'])
                          for container in pod['status'].get('containerStatuses', [])],
        })
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('Recorded', len(result['nodes']), 'nodes and', len(result['pods']), 'scoped workload identities')


if __name__ == '__main__':
    main()
