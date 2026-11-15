"""Measure public inference and automatic report availability on one frozen window."""
import argparse
import asyncio
import csv
import hashlib
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np

from bridge import Api, Bridge, redact


def save(path, value):
    path.write_text(redact(json.dumps(value, indent=2, allow_nan=False)) + '\n', encoding='utf-8')


def feature_key(features):
    values = []
    for name in sorted(features):
        value = float(features[name])
        if not math.isfinite(value):
            raise ValueError('Non-finite replay feature')
        if value == 0:
            value = 0.0
        values.append((name, value.hex()))
    return tuple(values)


def is_html_artifact(content_type, body):
    media_type = content_type.split(';', 1)[0].strip().lower()
    return media_type == 'text/html' and body.lstrip().startswith('<')


def audit_records(requests, responses, records):
    successful = [row for row in responses if row['valid_response']]
    expected = {row['prediction_id']: row for row in successful}
    actual = {str(row['public_id']): row for row in records}
    submitted = {row['request_id']: row for row in responses}
    if len(expected) != len(successful) or len(actual) != len(records):
        raise ValueError('Duplicate prediction IDs')
    if len(submitted) != len(responses) or len({row['request_id'] for row in records}) != len(records):
        raise ValueError('Duplicate request IDs')
    if not set(expected).issubset(actual):
        raise ValueError('Persisted IDs differ from valid response IDs')
    for prediction_id, stored in actual.items():
        response = submitted.get(stored['request_id'])
        if response is None:
            raise ValueError('Unexpected production request ID')
        if stored['request_id'] != response['request_id']:
            raise ValueError('Stored request ID differs from the submitted ID')
        if response['valid_response']:
            if prediction_id != response['prediction_id']:
                raise ValueError('Stored prediction ID differs from the API response')
            if str(stored['prediction']) != str(response['prediction']):
                raise ValueError('Stored prediction differs from the API response')
        inputs = requests[response['replay_index']]['body']['features']
        if feature_key(inputs) != feature_key(stored['features']):
            raise ValueError('Stored features differ from the frozen request')
    return {'matched_records': len(actual), 'unique_prediction_ids': len(actual),
            'unacknowledged_persisted_records': len(actual) - len(expected),
            'missing_request_ids': sorted(set(submitted) - {row['request_id'] for row in records})}


def load_bundle(bundle):
    checksums = json.loads((bundle / 'checksums.json').read_text())
    for relative_path, expected in checksums.items():
        if hashlib.sha256((bundle / relative_path).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Frozen artifact checksum differs: {relative_path}')
    manifest = json.loads((bundle / 'manifest.json').read_text())
    requests = [json.loads(line) for line in
                (bundle / 'windows/S0_n1000_s42/requests.jsonl').read_text().splitlines()]
    if len(requests) != 1000 or len(manifest['features']) != 52:
        raise ValueError('Expected the frozen 1,000-row, 52-feature S0 window')
    for row in requests:
        if set(row['body']['features']) != set(manifest['features']):
            raise ValueError('Replay feature schema differs from the frozen manifest')
    return manifest, requests


async def replay(requests, url, headers, prefix, rps, concurrency, output, close_event):
    semaphore = asyncio.Semaphore(concurrency)
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    responses = []
    closed = {}
    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=30, limits=limits, follow_redirects=False) as client:
        async def send(index, row):
            request_id = f'{prefix}{index:04d}'
            begin = time.perf_counter()
            if index == len(requests) - 1:
                closed.update(monotonic=begin, utc=datetime.now(timezone.utc).isoformat())
                close_event.set()
            result = {
                'replay_index': index, 'request_id': request_id,
                'sent_monotonic': begin, 'sent_offset_seconds': begin - started,
                'status_code': None, 'valid_response': False,
            }
            try:
                response = await client.post(url, json=row['body'],
                                             headers={**headers, 'X-Request-ID': request_id})
                result['latency_ms'] = (time.perf_counter() - begin) * 1000
                result['status_code'] = response.status_code
                result['returned_request_id'] = response.headers.get('x-request-id')
                if response.status_code == 200:
                    payload = response.json()
                    result.update(prediction_id=payload.get('prediction_id'), prediction=payload.get('prediction'))
                    result['valid_response'] = bool(payload.get('success') and result['prediction_id'])
            except (httpx.HTTPError, ValueError) as error:
                result['latency_ms'] = (time.perf_counter() - begin) * 1000
                result['error_type'] = type(error).__name__
            finally:
                result['finished_monotonic'] = time.perf_counter()
                responses.append(result)
                with output.open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(result, allow_nan=False) + '\n')
                semaphore.release()

        tasks = []
        for index, row in enumerate(requests):
            await asyncio.sleep(max(0, started + index / rps - time.perf_counter()))
            await semaphore.acquire()
            tasks.append(asyncio.create_task(send(index, row)))
        await asyncio.gather(*tasks)
    return sorted(responses, key=lambda row: row['replay_index']), closed


async def wait_report(api, monitor_id, event, output, timeout):
    await event.wait()
    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=45, follow_redirects=False) as client:
        while time.perf_counter() - started < timeout:
            headers = await asyncio.to_thread(api.headers)
            monitor_response = await client.get(api.base_url + f'/drift-monitors/{monitor_id}/', headers=headers)
            monitor_response.raise_for_status()
            runs = monitor_response.json()['runs']
            if runs:
                run = runs[0]
                if run['status'] in ('failed', 'cancelled', 'skipped'):
                    save(output / 'drift-run.json', run)
                    return {'status': run['status'], 'run_id': run['id']}
                if run['status'] == 'completed':
                    save(output / 'drift-run.json', run)
                    route = api.base_url + f"/drift-monitors/runs/{run['id']}"
                    data = await client.get(route + '/report-data/', headers=headers)
                    data.raise_for_status()
                    report_url = await client.get(route + '/report-url/', headers=headers)
                    report_url.raise_for_status()
                    # A separate request carries no bearer token to the object-storage host.
                    html = await client.get(report_url.json()['url'])
                    html.raise_for_status()
                    if not is_html_artifact(html.headers.get('content-type', ''), html.text):
                        raise ValueError('The available report is not HTML')
                    ready = time.perf_counter()
                    save(output / 'report-data.json', data.json())
                    (output / 'report.html').write_text(html.text, encoding='utf-8')
                    return {
                        'status': 'completed', 'run_id': run['id'], 'ready_monotonic': ready,
                        'ready_utc': datetime.now(timezone.utc).isoformat(),
                        'production_records': run['production_records'],
                        'summary': run['summary'],
                    }
            await asyncio.sleep(2)
    return {'status': 'timeout', 'timeout_seconds': timeout}


def wait_records(bridge, state, expected_ids, timeout=120, submitted_request_ids=None):
    deadline = time.monotonic() + timeout
    while True:
        records = bridge.records(state['project_id'], state['version_id'])
        ids = {str(row['public_id']) for row in records}
        if submitted_request_ids is not None:
            request_ids = {row['request_id'] for row in records}
            if not request_ids.issubset(submitted_request_ids):
                raise ValueError('Unexpected production request IDs')
            if set(expected_ids).issubset(ids):
                return records
        elif ids == set(expected_ids):
            return records
        if submitted_request_ids is None and not ids.issubset(set(expected_ids)):
            raise ValueError('The isolated version contains unexpected production IDs')
        if time.monotonic() >= deadline:
            return records
        time.sleep(3)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', required=True)
    parser.add_argument('--key', required=True)
    parser.add_argument('--owner', required=True)
    parser.add_argument('--api', required=True)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--rps', type=float, default=5)
    parser.add_argument('--concurrency', type=int, default=10)
    parser.add_argument('--report-timeout', type=int, default=900)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    manifest, inputs = load_bundle(args.bundle)
    with (args.bundle / 'scoring/S0_n1000_s42.csv').open(newline='') as stream:
        expected_predictions = [row['expected_pred_binary'] for row in csv.DictReader(stream)]
    state = json.loads((args.output / 'preparation.json').read_text())
    if not state['project_name'].startswith('csonet-timing-'):
        raise ValueError('The project is outside the benchmark namespace')
    bridge = Bridge(args.host, args.key, args.owner)
    api = Api(bridge, args.api)
    if bridge.records(state['project_id'], state['version_id']):
        raise ValueError('The benchmark version must start with no production records')
    run_prefix = 'ctiming-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
    if args.resume:
        prior = json.loads((args.output / 'measurement-manifest.json').read_text())
        if (prior['version_id'] != state['version_id'] or prior['target_rps'] != args.rps
                or prior['max_inflight'] != args.concurrency or prior['image_digest'] != state['image_digest']
                or prior['report_timeout_seconds'] != args.report_timeout):
            raise ValueError('Resume configuration differs from the original experiment')
        first_warmup = json.loads((args.output / 'warmup/requests.jsonl').read_text().splitlines()[0])
        run_prefix = first_warmup['request_id'].split('-warm-')[0]
    else:
        save(args.output / 'measurement-manifest.json', {
        'started_utc': datetime.now(timezone.utc).isoformat(), 'project_id': state['project_id'],
        'version_id': state['version_id'], 'model_sha256': manifest['model_sha256'],
        'reference_sha256': hashlib.sha256((args.bundle / manifest['reference']).read_bytes()).hexdigest(),
        'window_id': 'S0_n1000_s42', 'window_size': 1000, 'feature_count': 52,
        'target_rps': args.rps, 'max_inflight': args.concurrency, 'poll_interval_seconds': 2,
        'report_timeout_seconds': args.report_timeout, 'percentile_method': 'linear',
        'retry_policy': 'No client inference retries', 'image_digest': state['image_digest'],
        })
        warmup = args.output / 'warmup'
        warmup.mkdir(exist_ok=False)
        warm_prefix = run_prefix + '-warm-'
        responses, _ = asyncio.run(replay(inputs[:50], state['predict_url'], api.headers(), warm_prefix,
                                         args.rps, args.concurrency, warmup / 'requests.jsonl', asyncio.Event()))
        expected = [row['prediction_id'] for row in responses if row['valid_response']]
        records = wait_records(bridge, state, expected)
        save(warmup / 'records.json', records)
        audit_records(inputs[:50], responses, records)
        if len(expected) != 50:
            raise ValueError('Warm-up had failed requests; investigate before measurement')
        if any(str(row.get('prediction')) != expected_predictions[row['replay_index']] for row in responses):
            raise ValueError('Warm-up predictions differ from the frozen baseline')
        save(warmup / 'cleanup.json', bridge.cleanup(state['project_id'], state['version_id'], expected, warm_prefix))
    summaries = []
    for repeat in range(1, 4):
        destination = args.output / f'repeat_{repeat}'
        if args.resume and (destination / 'summary.json').exists():
            if json.loads((destination / 'cleanup.json').read_text())['remaining'] != 0:
                raise ValueError('Previous repeat was not cleaned up')
            summaries.append(json.loads((destination / 'summary.json').read_text()))
            print('Retained measured repeat', repeat, flush=True)
            continue
        destination.mkdir(exist_ok=False)
        prefix = f'{run_prefix}-r{repeat}-'
        monitor = api.call('POST', '/drift-monitors/', json={
            'version': state['version_id'], 'name': prefix.rstrip('-'),
            'trigger_threshold': 1000, 'is_active': True,
        })
        save(destination / 'monitor.json', {key: monitor[key] for key in ('id', 'name', 'version_id', 'trigger_threshold')})
        print('Measuring repeat', repeat, 'monitor', monitor['id'], flush=True)
        api.token = None
        inference_headers = api.headers()

        async def measure():
            event = asyncio.Event()
            observation = asyncio.create_task(wait_report(api, monitor['id'], event, destination, args.report_timeout))
            responses, closed = await replay(inputs, state['predict_url'], inference_headers, prefix, args.rps,
                                             args.concurrency, destination / 'requests.jsonl', event)
            if any(not row['valid_response'] for row in responses):
                # A client transport error may occur after the server accepted a request.
                await asyncio.sleep(120)
                current = await asyncio.to_thread(bridge.records, state['project_id'], state['version_id'])
                if len(current) < len(inputs):
                    observation.cancel()
                    try:
                        await observation
                    except asyncio.CancelledError:
                        pass
                    return (responses, closed), {'status': 'not_triggered_incomplete_window',
                                                  'production_records': len(current)}
            return (responses, closed), await observation

        (responses, closed), report = asyncio.run(measure())
        save(destination / 'report-observation.json', report)
        expected = [row['prediction_id'] for row in responses if row['valid_response']]
        records = wait_records(bridge, state, expected, submitted_request_ids={row['request_id'] for row in responses})
        save(destination / 'records.json', records)
        audit = audit_records(inputs, responses, records)
        save(destination / 'record-audit.json', audit)
        indices = {row['request_id']: row['replay_index'] for row in responses}
        mismatches = sum(str(row['prediction']) != expected_predictions[indices[row['request_id']]] for row in records)
        valid = (len(records) == 1000 and report['status'] == 'completed'
                 and report['production_records'] == 1000 and mismatches == 0)
        successful_latencies = [row['latency_ms'] for row in responses if row['valid_response']]
        send_span = max(row['sent_monotonic'] for row in responses) - min(row['sent_monotonic'] for row in responses)
        summary = {
            'repeat': repeat, 'valid_measurement': valid, 'attempts': len(responses),
            'valid_responses': len(expected), 'http_or_response_failures': len(responses) - len(expected),
            'persisted_records': len(records),
            'prediction_mismatches_from_frozen_baseline': mismatches,
            'inference_p95_ms': float(np.quantile(successful_latencies, .95, method='linear')) if expected else None,
            'actual_dispatch_rps': (len(responses) - 1) / send_span,
            'window_closed_utc': closed['utc'], 'report_status': report['status'],
            'window_to_report_seconds': report['ready_monotonic'] - closed['monotonic'] if report['status'] == 'completed' else None,
        }
        save(destination / 'summary.json', summary)
        summaries.append(summary)
        print(json.dumps(summary), flush=True)
        api.call('PATCH', f"/drift-monitors/{monitor['id']}/", json={'is_active': False})
        save(destination / 'cleanup.json', bridge.cleanup(state['project_id'], state['version_id'],
                                                          [row['public_id'] for row in records], prefix))
        time.sleep(5)
    save(args.output / 'summary.json', {
        'complete': True, 'repeats': summaries,
        'complete_windows': sum(row['valid_measurement'] for row in summaries),
        'report_timing_repeats': sum(row['window_to_report_seconds'] is not None for row in summaries),
        'total_client_failures': sum(row['http_or_response_failures'] for row in summaries),
        'median_inference_p95_ms': float(np.median([row['inference_p95_ms'] for row in summaries])),
        'median_window_to_report_seconds': float(np.median([row['window_to_report_seconds'] for row in summaries
                                                          if row['window_to_report_seconds'] is not None]))
                                          if any(row['window_to_report_seconds'] is not None for row in summaries) else None,
    })
    print('Three planned repeats recorded and audited.', flush=True)


if __name__ == '__main__':
    main()
