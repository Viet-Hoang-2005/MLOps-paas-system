"""Reproducible, isolated NIDS fixed-model drift experiment. Never edits source CSVs."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import platform
import subprocess
import time
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy
from scipy.stats import ks_2samp
import sklearn
from sklearn.metrics import confusion_matrix, f1_score, roc_auc_score
import xgboost
from xgboost import XGBClassifier

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def canonical_features(df, cols):
    x = df[cols].apply(pd.to_numeric, errors='coerce').astype('float64')
    # Exact canonical numeric identity, independent of label or CSV textual formatting.
    a = np.ascontiguousarray(x.to_numpy(), dtype='<f8')
    a[a == 0] = 0.0
    a[np.isnan(a)] = np.nan
    hashes = [hashlib.sha256(row.tobytes()).hexdigest() for row in a]
    return x, pd.Series(hashes, index=df.index)


def read_data(path):
    d = pd.read_csv(path)
    d.columns = d.columns.str.strip()
    assert not d.columns.duplicated().any(), 'Duplicate column names'
    if 'Label' not in d and 'Attack Type' in d:
        d = d.rename(columns={'Attack Type': 'Label'})
    assert 'Label' in d
    d['Label'] = d.Label.astype(str).str.strip()
    return d


def prepare(c, out):
    source = ROOT / c['source']
    d = read_data(source)
    cols = [x for x in d if x != 'Label']
    x, hashes = canonical_features(d, cols)
    expected_labels = set(c['known_labels'] + c['novel_labels'])
    assert set(d.Label) == expected_labels
    assert len(cols) == 52
    d[cols] = x
    d['row_id'] = np.arange(len(d))
    d['feature_sha256'] = hashes
    finite = np.isfinite(x.to_numpy()).all(axis=1)
    conflicts = d.groupby('feature_sha256').Label.nunique()
    conflict_ids = set(conflicts[conflicts > 1].index)
    conflict_mask = d.feature_sha256.isin(conflict_ids)
    excluded = d.loc[~finite | conflict_mask, ['row_id', 'Label', 'feature_sha256']].copy()
    excluded['reason'] = ['nonfinite' if not finite[i] else 'conflicting_labels' for i in excluded.index]
    excluded.to_csv(out / 'excluded_rows.csv', index=False)
    clean = d.loc[finite & ~conflict_mask].copy()
    dedup = clean.duplicated('feature_sha256', keep='first')
    clean.loc[dedup, ['row_id','Label','feature_sha256']].to_csv(out / 'duplicate_rows_removed.csv', index=False)
    clean = clean.loc[~dedup].copy()
    audit = {
        'source_path': c['source'], 'source_sha256': sha(source),
        'raw_rows': len(d), 'features': cols, 'raw_label_counts': d.Label.value_counts().to_dict(),
        'nonfinite_rows': int((~finite).sum()), 'conflicting_feature_groups': len(conflict_ids),
        'rows_in_conflicting_groups': int(conflict_mask.sum()),
        'duplicate_rows_removed_after_conflict_exclusion': int(dedup.sum()),
        'clean_rows': len(clean), 'clean_label_counts': clean.Label.value_counts().to_dict(),
        'source_preprocessing_warning': 'Upstream globally selected features/removed categories; current splits do not undo upstream preprocessing.',
        'temporal_metadata_present': [col for col in cols if any(t in col.lower() for t in ['timestamp','capture','session','date'])],
        'identity': 'SHA256 of ordered little-endian float64 feature bytes; label excluded; signed zero normalized; exact equality only'
    }
    dump(out / 'dataset_manifest.json', audit)
    summaries, sets = [], {}
    for p in sorted((ROOT / 'data').glob('*.csv')):
        try:
            a = read_data(p)
            if set(a.columns) != set(cols + ['Label']):
                summaries.append({'file': p.name, 'rows': len(a), 'schema_matches': False, 'sha256': sha(p)})
                continue
            xx, hh = canonical_features(a, cols)
            sets[p.name] = set(hh)
            summaries.append({'file': p.name, 'rows': len(a), 'schema_matches': True,
                              'sha256': sha(p), 'label_counts': a.Label.value_counts().to_dict(),
                              'duplicate_feature_rows': int(hh.duplicated().sum()),
                              'nonfinite_rows': int((~np.isfinite(xx.to_numpy()).all(axis=1)).sum())})
        except (ValueError, KeyError) as e:
            summaries.append({'file': p.name, 'error': str(e)})
    dump(out / 'source_file_audit.json', summaries)
    pairs = [{'file_a': a, 'file_b': b, 'shared_unique_feature_rows': len(sets[a] & sets[b])}
             for a,b in itertools.combinations(sets,2)]
    pd.DataFrame(pairs).to_csv(out / 'source_file_overlap.csv', index=False)
    clean['split'] = ''
    rng = np.random.default_rng(c['split_seed'])
    for label in sorted(expected_labels):
        ids = rng.permutation(clean.index[clean.Label == label])
        pos = 0
        for k, (name, frac) in enumerate(c['split_fractions'].items()):
            end = len(ids) if k == 3 else pos + int(len(ids) * frac)
            clean.loc[ids[pos:end], 'split'] = name
            pos = end
    clean['used_for_model_fit'] = (clean.split == 'train') & clean.Label.isin(c['known_labels'])
    clean[['row_id','feature_sha256','Label','split','used_for_model_fit']].to_csv(out / 'split_manifest.csv.gz', index=False)
    counts = pd.crosstab(clean.split, clean.Label)
    counts.to_csv(out / 'split_counts.csv')
    splitsets = {k:set(clean.loc[clean.split == k,'feature_sha256']) for k in c['split_fractions']}
    overlap = {f'{a}__{b}':len(splitsets[a]&splitsets[b]) for a,b in itertools.combinations(splitsets,2)}
    assert not any(overlap.values())
    assert clean.feature_sha256.is_unique and (clean.split != '').all()
    dump(out / 'split_overlap.json', {'shared_feature_rows':overlap, 'all_zero':True})
    print('AUDIT', json.dumps({k:audit[k] for k in ['raw_rows','clean_rows','conflicting_feature_groups','rows_in_conflicting_groups','duplicate_rows_removed_after_conflict_exclusion']}), flush=True)
    print(counts.to_string(), flush=True)
    return clean.set_index('row_id', drop=False), cols


def sample_window(pool, n, attack_fraction, replacement, seed, c):
    n_attack = int(round(n * attack_fraction))
    n_novel = int(round(n_attack * replacement))
    counts = {'BENIGN':n-n_attack, 'DDoS':n_attack-n_novel}
    q,r = divmod(n_novel,len(c['novel_labels']))
    counts.update({label:q+(i<r) for i,label in enumerate(c['novel_labels'])})
    rng = np.random.default_rng(seed)
    ids = []
    for label,n_label in counts.items():
        choices = pool.index[pool.Label == label].to_numpy()
        assert n_label <= len(choices), (label,n_label,len(choices))
        ids.extend(rng.choice(choices, n_label, replace=False).tolist())
    assert len(set(ids)) == n
    return pool.loc[rng.permutation(ids)], counts


def bh(p):
    p = np.asarray(p)
    order = np.argsort(p)
    q = np.minimum.accumulate((p[order]*len(p)/np.arange(1,len(p)+1))[::-1])[::-1]
    ans = np.empty_like(q)
    ans[order] = np.clip(q,0,1)
    return ans


def measure(w, ref, model, cols, c, wid, scenario, seed, attack_fraction, replacement):
    x = w[cols]
    y = (w.Label != 'BENIGN').astype(int).to_numpy()
    prob = model.predict_proba(x)[:,1]
    pred = (prob >= c['decision_threshold']).astype(int)
    tn,fp,fn,tp = confusion_matrix(y,pred,labels=[0,1]).ravel()
    stats = [ks_2samp(ref[col], x[col], alternative='two-sided', method='asymp') for col in cols]
    p = np.array([s.pvalue for s in stats]); q = bh(p)
    passed = q < c['alpha']
    frows = [{'window_id':wid,'feature':col,'ks':float(s.statistic),'p_value':float(s.pvalue),
              'bh_q':float(qq),'raw_drift':bool(s.pvalue<c['alpha']),'bh_drift':bool(ok)}
             for col,s,qq,ok in zip(cols,stats,q,passed)]
    row = {'window_id':wid,'scenario':scenario,'seed':seed,'n':len(w),'attack_fraction':attack_fraction,
           'novel_replacement':replacement,'drift_share':float(passed.mean()),
           'uncorrected_drift_share':float((p<c['alpha']).mean()),
           'mean_ks':float(np.mean([s.statistic for s in stats])),
           'max_ks':float(max(s.statistic for s in stats)),
           'macro_f1':float(f1_score(y,pred,average='macro',zero_division=0)),
           'attack_recall':float(tp/(tp+fn)), 'benign_fpr':float(fp/(fp+tn)),
           'roc_auc':float(roc_auc_score(y,prob)),
           'tn':int(tn),'fp':int(fp),'fn':int(fn),'tp':int(tp)}
    for label in ['BENIGN','DDoS']+c['novel_labels']:
        mask = (w.Label == label).to_numpy()
        row[f'n_{label}'] = int(mask.sum())
        row[f'recall_{label}'] = float(np.mean(pred[mask] == (label != 'BENIGN'))) if mask.any() else None
    return row,frows


def summarize(out,c):
    m = pd.read_csv(out/'window_metrics.csv')
    main = m[m.seed.isin(c['main_seeds'])]
    summary = main.groupby(['scenario','n']).agg(
        windows=('window_id','size'), drift_mean=('drift_share','mean'),drift_std=('drift_share','std'),
        ks_mean=('mean_ks','mean'),macro_f1_mean=('macro_f1','mean'),macro_f1_std=('macro_f1','std'),
        recall_mean=('attack_recall','mean'),recall_std=('attack_recall','std'),
        fpr_mean=('benign_fpr','mean'),fpr_std=('benign_fpr','std')).reset_index()
    summary.to_csv(out/'scenario_summary.csv',index=False)
    alerts = []
    for (sc,n),g in m.groupby(['scenario','n']):
        for tau in c['thresholds']:
            alerts.append({'scenario':sc,'n':int(n),'threshold':tau,'windows':len(g),
                           'alerts_bh':int((g.drift_share>=tau).sum()),
                           'alert_rate_bh':float((g.drift_share>=tau).mean()),
                           'alert_rate_uncorrected':float((g.uncorrected_drift_share>=tau).mean())})
    a = pd.DataFrame(alerts); a.to_csv(out/'threshold_summary.csv',index=False)
    fig,axs = plt.subplots(1,2,figsize=(12,4.5),constrained_layout=True)
    scenarios = list(main.scenario.drop_duplicates())
    for ax,n in zip(axs,c['window_sizes']):
        p = a[a.n==n].pivot(index='scenario',columns='threshold',values='alert_rate_bh').reindex(scenarios)
        im=ax.imshow(p.to_numpy(),vmin=0,vmax=1,cmap='Blues',aspect='auto')
        ax.set_xticks(range(len(p.columns)),[str(t) for t in p.columns]); ax.set_yticks(range(len(p.index)),p.index)
        for i in range(len(p.index)):
            for j in range(len(p.columns)):
                val=p.iloc[i,j]; ax.text(j,i,f'{val:.0%}',ha='center',va='center',color='white' if val>.6 else 'black')
        ax.set_xlabel('Drift-share threshold'); ax.set_title(f'Current window n={n}')
    fig.colorbar(im,ax=axs,label='Alert frequency (BH-corrected KS)')
    fig.savefig(out/'threshold_sensitivity.png',dpi=170); fig.savefig(out/'threshold_sensitivity.pdf'); plt.close(fig)
    fig,axs = plt.subplots(2,2,figsize=(12,7),constrained_layout=True)
    fields=[('drift_mean','drift_std','Drift share'),('macro_f1_mean','macro_f1_std','Macro-F1'),
            ('recall_mean','recall_std','Attack recall'),('fpr_mean','fpr_std','Benign false-positive rate')]
    for ax,(metric,sd,title) in zip(axs.flat,fields):
        for n in c['window_sizes']:
            p=summary[summary.n==n].set_index('scenario').reindex(scenarios)
            ax.errorbar(range(len(p)),p[metric],yerr=p[sd],marker='o',capsize=3,label=f'n={n}')
        ax.set_xticks(range(len(scenarios)),scenarios,rotation=25,ha='right'); ax.set_title(title); ax.grid(alpha=.25); ax.legend()
        if metric!='fpr_mean': ax.set_ylim(-.03,1.03)
    fig.suptitle('Fixed model: controlled shift; mean ± sampling SD (5 seeds)')
    fig.savefig(out/'drift_vs_performance.png',dpi=170); fig.savefig(out/'drift_vs_performance.pdf'); plt.close(fig)
    print(summary.to_string(index=False),flush=True)


def run(c,out):
    t0=time.perf_counter(); out.mkdir(parents=True,exist_ok=False)
    dump(out/'config.json',c)
    dump(out/'environment.json',{'python':platform.python_version(),'platform':platform.platform(),
        'versions':{k:v.__version__ for k,v in [('pandas',pd),('numpy',np),('scipy',scipy),('scikit-learn',sklearn),('xgboost',xgboost),('matplotlib',matplotlib)]},
        'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'runner_sha256':sha(Path(__file__))})
    d,cols=prepare(c,out)
    train=d[d.used_for_model_fit]
    ref,counts=sample_window(d[d.split=='reference'],c['reference_size'],c['baseline_attack_fraction'],0,c['split_seed']+1,c)
    ref[['row_id','feature_sha256','Label']].to_csv(out/'reference_manifest.csv',index=False)
    model=XGBClassifier(**c['xgboost'])
    start=time.perf_counter(); model.fit(train[cols],(train.Label!='BENIGN').astype(int)); elapsed=time.perf_counter()-start
    model.save_model(out/'baseline.ubj')
    dump(out/'model_manifest.json',{'model_sha256':sha(out/'baseline.ubj'),'train_rows':len(train),
        'train_label_counts':train.Label.value_counts().to_dict(),'features':cols,
        'training_seconds':elapsed,'reference_counts':counts,'preprocessing':'ordered numeric features, no scaler; nonfinite rows excluded before split; fixed upstream feature selection'})
    print(f'TRAINED {len(train)} rows in {elapsed:.2f}s',flush=True)
    # Development pilot validates plumbing; no configuration tuning or pass/fail on favorable scores.
    prows=[]
    for sc,frac in [('pilot_stable',.3),('pilot_ratio',.5)]:
        w,_=sample_window(d[d.split=='development'],500,frac,0,2026,c)
        row,_=measure(w,ref,model,cols,c,sc,sc,2026,frac,0); prows.append(row)
    pd.DataFrame(prows).to_csv(out/'pilot_metrics.csv',index=False)
    assert np.isfinite(pd.DataFrame(prows)[['macro_f1','mean_ks','drift_share']].to_numpy()).all()
    print('PILOT',pd.DataFrame(prows)[['scenario','drift_share','macro_f1']].to_json(orient='records'),flush=True)
    scenarios=[('S0',c['baseline_attack_fraction'],0)]
    scenarios += [(f'S1_a{int(a*100)}',a,0) for a in c['s1_attack_fractions']]
    scenarios += [(f'S2_r{int(r*100)}',c['baseline_attack_fraction'],r) for r in c['s2_replacement_fractions']]
    rows=[]; features=[]; membership=[]; eval_pool=d[d.split=='evaluation']
    ref_ids=set(ref.index); train_ids=set(train.index)
    for sc,frac,replacement in scenarios:
        for n in c['window_sizes']:
            seeds=c['main_seeds']+(c['additional_stable_seeds'] if sc=='S0' else [])
            for seed in seeds:
                wid=f'{sc}_n{n}_s{seed}'
                w,_=sample_window(eval_pool,n,frac,replacement,seed,c)
                assert not (set(w.index)&(ref_ids|train_ids))
                row,ff=measure(w,ref,model,cols,c,wid,sc,seed,frac,replacement)
                rows.append(row); features.extend(ff)
                membership.extend({'window_id':wid,'row_id':int(i)} for i in w.index)
            print(f'DONE {sc} n={n} windows={len(seeds)}',flush=True)
    pd.DataFrame(rows).to_csv(out/'window_metrics.csv',index=False)
    pd.DataFrame(features).to_csv(out/'feature_drift.csv.gz',index=False)
    pd.DataFrame(membership).to_csv(out/'window_membership.csv.gz',index=False)
    assert len(rows)==120
    summarize(out,c)
    assert sha(ROOT/c['source'])==json.loads((out/'dataset_manifest.json').read_text(encoding='utf-8'))['source_sha256']
    dump(out/'completion.json',{'status':'complete','windows':len(rows),'feature_tests':len(features),
        'total_seconds':time.perf_counter()-t0,'all_split_overlap_zero':True,'input_source_unchanged':True})
    print(f'COMPLETE {out} elapsed={time.perf_counter()-t0:.1f}s',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--config',type=Path,default=HERE/'config.json'); p.add_argument('--output',type=Path,required=True)
    args=p.parse_args(); run(json.loads(args.config.read_text(encoding='utf-8')),args.output.resolve())
