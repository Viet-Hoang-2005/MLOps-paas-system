import math
import json
import pytest

from benchmark_production import audit_records, feature_key, is_html_artifact, save


def test_saved_report_removes_presigned_query_and_preserves_metrics(tmp_path):
    destination = tmp_path / 'report.json'
    save(destination, {'url': 'https://storage.example/report?X-Amz-Signature=example',
                       'metrics': {'drift_share': 0.125, 'records': 1000}})
    result = json.loads(destination.read_text())
    assert result['url'] == 'https://storage.example/report?[redacted]'
    assert result['metrics'] == {'drift_share': 0.125, 'records': 1000}


def sample():
    requests = [{'body': {'features': {'a': 0.0, 'b': 2.5}}}]
    responses = [{'valid_response': True, 'prediction_id': 'id-1', 'request_id': 'req-1',
                  'prediction': 0, 'replay_index': 0}]
    records = [{'public_id': 'id-1', 'request_id': 'req-1', 'prediction': '0',
                'features': {'b': 2.5, 'a': 0}}]
    return requests, responses, records


def test_audit_preserves_zero_prediction_and_ignores_feature_order():
    assert audit_records(*sample())['matched_records'] == 1


def test_audit_rejects_missing_record():
    requests, responses, _ = sample()
    with pytest.raises(ValueError, match='IDs differ'):
        audit_records(requests, responses, [])


def test_audit_rejects_duplicate_record():
    requests, responses, records = sample()
    with pytest.raises(ValueError, match='Duplicate'):
        audit_records(requests, responses, records + records)


def test_audit_rejects_blank_zero_and_changed_feature():
    requests, responses, records = sample()
    records[0]['prediction'] = ''
    with pytest.raises(ValueError, match='prediction differs'):
        audit_records(requests, responses, records)
    records[0]['prediction'] = '0'
    records[0]['features']['b'] = math.nextafter(2.5, 3)
    with pytest.raises(ValueError, match='features differ'):
        audit_records(requests, responses, records)


def test_feature_key_rejects_nonfinite_values():
    with pytest.raises(ValueError, match='Non-finite'):
        feature_key({'a': float('nan')})


def test_signed_zero_matches_after_jsonb_normalization():
    assert feature_key({'a': -0.0}) == feature_key({'a': 0.0})


def test_evidently_script_fragment_is_a_valid_html_artifact():
    assert is_html_artifact('text/html; charset=utf-8', '\n  <script>window.evidently = {};</script>')
    assert not is_html_artifact('application/json', '{"html":"<html>"}')


def test_client_error_with_persisted_record_is_audited_by_request_id():
    requests, responses, records = sample()
    responses[0] = {'valid_response': False, 'request_id': 'req-1', 'replay_index': 0}
    result = audit_records(requests, responses, records)
    assert result['unacknowledged_persisted_records'] == 1
    assert result['missing_request_ids'] == []


def test_client_error_without_record_retains_missing_request_id():
    requests, responses, _ = sample()
    responses[0] = {'valid_response': False, 'request_id': 'req-1', 'replay_index': 0}
    result = audit_records(requests, responses, [])
    assert result['matched_records'] == 0
    assert result['missing_request_ids'] == ['req-1']
