"""Post-hoc diagnostics of the frozen run, without fitting or changing thresholds."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from xgboost import XGBClassifier

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
RUN = HERE / 'results/run_20260926'
OUT = HERE / 'diagnostics/run_20260927'


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((RUN / 'model_manifest.json').read_text())
    c = json.loads((RUN / 'config.json').read_text())
    source = pd.read_csv(ROOT / c['source'])
    source.columns = source.columns.str.strip()
    source = source.rename(columns={'Attack Type': 'Label'})
    split = pd.read_csv(RUN / 'split_manifest.csv.gz')
    evaluation = source.loc[split.loc[split.split.eq('evaluation'), 'row_id']].copy()
    model = XGBClassifier()
    model.load_model(RUN / 'baseline.ubj')
    prob = model.predict_proba(evaluation[manifest['features']])[:, 1]
    evaluation['attack_probability'] = prob
    evaluation['predicted_attack'] = prob >= c['decision_threshold']
    rows = []
    for label, group in evaluation.groupby('Label'):
        rows.append({'label': label, 'rows': len(group), 'predicted_attack': int(group.predicted_attack.sum()),
                     'attack_prediction_rate': group.predicted_attack.mean(),
                     'mean_attack_probability': group.attack_probability.mean(),
                     'median_attack_probability': group.attack_probability.median(),
                     'p05_attack_probability': group.attack_probability.quantile(.05),
                     'p95_attack_probability': group.attack_probability.quantile(.95)})
    pd.DataFrame(rows).to_csv(OUT / 'full_evaluation_pool_by_family.csv', index=False)
    gains = model.get_booster().get_score(importance_type='total_gain')
    gain = pd.DataFrame([{'feature': f, 'total_gain': gains.get(f, 0)} for f in manifest['features']])
    gain['gain_fraction'] = gain.total_gain / gain.total_gain.sum()
    gain.sort_values('total_gain', ascending=False).to_csv(OUT / 'model_feature_gain.csv', index=False)
    membership = pd.read_csv(RUN / 'window_membership.csv.gz')
    metrics = pd.read_csv(RUN / 'window_metrics.csv')
    membership = membership.merge(metrics[['window_id', 'scenario', 'seed', 'n']], on='window_id', validate='many_to_one')
    membership['label'] = source.loc[membership.row_id, 'Label'].to_numpy()
    reuse = membership.groupby(['scenario', 'n', 'label']).agg(appearances=('row_id', 'size'), unique_rows=('row_id', 'nunique')).reset_index()
    reuse.to_csv(OUT / 'window_sample_reuse.csv', index=False)
    decomposition = []
    for row in metrics[metrics.scenario.str.startswith('S2')].itertuples():
        novel_n = sum(getattr(row, 'n_' + k) for k in c['novel_labels'])
        novel_tp = sum(getattr(row, 'n_' + k) * getattr(row, 'recall_' + k) for k in c['novel_labels'])
        known_tp = row.n_DDoS * (row.recall_DDoS if row.n_DDoS else 0)
        reconstructed = (known_tp + novel_tp) / (row.n_DDoS + novel_n)
        assert np.isclose(reconstructed, row.attack_recall)
        decomposition.append({'window_id': row.window_id, 'scenario': row.scenario, 'n': row.n,
                              'replacement': row.novel_replacement, 'novel_recall': novel_tp / novel_n,
                              'known_recall': row.recall_DDoS, 'overall_attack_recall': row.attack_recall,
                              'mixture_reconstructed_recall': reconstructed})
    pd.DataFrame(decomposition).to_csv(OUT / 'recall_decomposition.csv', index=False)
    out = {'scope': 'Post-hoc analysis of existing fixed model and evaluation pool; no model fit, threshold tuning, or new confirmatory test.',
           'input_sha256': hashlib.sha256((ROOT / c['source']).read_bytes()).hexdigest(),
           'model_sha256': hashlib.sha256((RUN / 'baseline.ubj').read_bytes()).hexdigest(),
           'evaluation_rows': len(evaluation), 'top_gain_features': gain.sort_values('total_gain', ascending=False).head(5).to_dict('records'),
           'recall_decomposition_all_windows_match': True,
           'caution': 'Gain is training attribution, not causal importance or proof of a shortcut. Whole-pool diagnosis is post-hoc, not an independent dataset.'}
    assert out['model_sha256'] == manifest['model_sha256']
    assert out['input_sha256'] == json.loads((RUN / 'dataset_manifest.json').read_text())['source_sha256']
    (OUT / 'diagnostic_manifest.json').write_text(json.dumps(out, indent=2), encoding='utf-8')
    print(pd.DataFrame(rows).to_string(index=False))
    print(gain.sort_values('total_gain', ascending=False).head(5).to_string(index=False))


if __name__ == '__main__':
    main()
