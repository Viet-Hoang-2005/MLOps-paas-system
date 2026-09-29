"""Independent checks of persisted artifacts; does not import the experiment runner."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import false_discovery_control, ks_2samp
from sklearn.metrics import confusion_matrix, f1_score, roc_auc_score
from xgboost import XGBClassifier

ROOT = Path(__file__).resolve().parents[4]


def checksum(path):
    return hashlib.file_digest(open(path, 'rb'), 'sha256').hexdigest()


def verify(out):
    def read(name):
        return json.loads((out / name).read_text(encoding='utf-8'))
    c = read('config.json')
    audit = read('dataset_manifest.json')
    for entry in read('source_file_audit.json'):
        assert checksum(ROOT / 'data' / entry['file']) == entry['sha256']
    source = pd.read_csv(ROOT / c['source'])
    source.columns = source.columns.str.strip()
    source = source.rename(columns={'Attack Type': 'Label'})
    source.Label = source.Label.str.strip()
    cols = audit['features']
    a = np.ascontiguousarray(source[cols].to_numpy(dtype='float64'), dtype='<f8')
    a[a == 0] = 0.0
    hashes = pd.Series([hashlib.sha256(row.tobytes()).hexdigest() for row in a])
    split = pd.read_csv(out / 'split_manifest.csv.gz')
    assert split.row_id.is_unique and split.feature_sha256.is_unique
    assert (hashes.loc[split.row_id].to_numpy() == split.feature_sha256.to_numpy()).all()
    assert (source.loc[split.row_id, 'Label'].to_numpy() == split.Label.to_numpy()).all()
    assert len(split) == audit['clean_rows']
    assert np.isfinite(a[split.row_id]).all()
    excluded = pd.read_csv(out / 'excluded_rows.csv')
    duplicates = pd.read_csv(out / 'duplicate_rows_removed.csv')
    accounted = list(split.row_id) + list(excluded.row_id) + list(duplicates.row_id)
    assert len(accounted) == len(source) == len(set(accounted))
    label_counts = source.Label.groupby(hashes).nunique()
    conflict = set(label_counts[label_counts > 1].index)
    assert set(hashes.loc[excluded.row_id]) == conflict
    assert all(hashes.loc[i] in set(split.feature_sha256) for i in duplicates.row_id)
    train = split[split.used_for_model_fit]
    assert set(train.Label) == {'BENIGN', 'DDoS'} and (train.split == 'train').all()
    assert len(train) == read('model_manifest.json')['train_rows']
    membership = pd.read_csv(out / 'window_membership.csv.gz')
    metrics = pd.read_csv(out / 'window_metrics.csv').set_index('window_id')
    features = pd.read_csv(out / 'feature_drift.csv.gz')
    ref = pd.read_csv(out / 'reference_manifest.csv')
    pools = split.set_index('row_id').split
    assert (pools.loc[ref.row_id] == 'reference').all()
    assert ref.row_id.is_unique and len(ref) == c['reference_size']
    assert (pools.loc[membership.row_id] == 'evaluation').all()
    assert checksum(out / 'baseline.ubj') == read('model_manifest.json')['model_sha256']
    model = XGBClassifier()
    model.load_model(out / 'baseline.ubj')
    for wid, group in membership.groupby('window_id'):
        m = metrics.loc[wid]
        assert group.row_id.is_unique and len(group) == m['n']
        window = source.loc[group.row_id]
        y = window.Label.ne('BENIGN').astype(int)
        prob = model.predict_proba(window[cols])[:, 1]
        pred = prob >= c['decision_threshold']
        cm = confusion_matrix(y, pred, labels=[0, 1]).ravel()
        np.testing.assert_array_equal(cm, m[['tn', 'fp', 'fn', 'tp']].to_numpy())
        tn, fp, fn, tp = cm
        actual = [f1_score(y, pred, average='macro'), tp / (tp + fn), fp / (fp + tn), roc_auc_score(y, prob)]
        np.testing.assert_allclose(actual, m[['macro_f1', 'attack_recall', 'benign_fpr', 'roc_auc']].to_numpy(dtype=float), atol=1e-12)
        for label in c['known_labels'] + c['novel_labels']:
            mask = window.Label.eq(label).to_numpy()
            assert mask.sum() == m['n_' + label]
            if mask.any():
                np.testing.assert_allclose(np.mean(pred[mask] == (label != 'BENIGN')), m['recall_' + label], atol=1e-12)
        stored = features[features.window_id == wid].set_index('feature').loc[cols]
        stats = [ks_2samp(source.loc[ref.row_id, col], window[col], method='asymp') for col in cols]
        p = np.array([s.pvalue for s in stats])
        q = false_discovery_control(p, method='bh')
        np.testing.assert_allclose(stored.p_value, p, atol=1e-12)
        np.testing.assert_allclose(stored.ks, [s.statistic for s in stats], atol=1e-12)
        np.testing.assert_allclose(stored.bh_q, q, atol=1e-12)
        np.testing.assert_array_equal(stored.bh_drift, q < c['alpha'])
        np.testing.assert_allclose(m.drift_share, np.mean(q < c['alpha']), atol=1e-12)
    thresholds = pd.read_csv(out / 'threshold_summary.csv')
    for r in thresholds.itertuples():
        rows = metrics[(metrics.scenario == r.scenario) & (metrics.n == r.n)]
        assert len(rows) == r.windows
        assert int((rows.drift_share >= r.threshold).sum()) == r.alerts_bh
        np.testing.assert_allclose((rows.uncorrected_drift_share >= r.threshold).mean(), r.alert_rate_uncorrected, atol=1e-12)
    assert len(metrics) == 120 and len(features) == 6240
    assert set(membership.window_id) == set(metrics.index)
    for n in c['window_sizes']:
        assert len(metrics[(metrics.scenario == 'S0') & (metrics.n == n)]) == 30
    result = {'status': 'passed', 'windows_rechecked': len(metrics), 'ks_tests_recomputed': len(features),
              'checks': ['all source CSV checksums unchanged', 'canonical identities and exclusion accounting',
                         'unique feature vectors across all four pools', 'window membership belongs to evaluation only',
                         'persisted model checksum and recomputed metrics', 'all KS tests recomputed',
                         'BH independently checked with scipy.stats.false_discovery_control', 'threshold alert counts'],
              'verifier_sha256': checksum(Path(__file__))}
    (out / 'verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('results', type=Path)
    verify(parser.parse_args().results.resolve())
