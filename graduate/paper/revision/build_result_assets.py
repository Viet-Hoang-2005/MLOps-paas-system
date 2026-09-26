"""Build manuscript assets from frozen CSVs without modifying experiment artifacts."""
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

HERE = Path(__file__).resolve().parent
RUN = HERE.parent / 'experiments/drift_only/results/run_20260926'
SCENARIOS = ['S0', 'S1_a15', 'S1_a50', 'S1_a85', 'S2_r25', 'S2_r50', 'S2_r100']
LABELS = ['S0', r'S1 (15\%)', r'S1 (50\%)', r'S1 (85\%)', r'S2 (25\%)', r'S2 (50\%)', r'S2 (100\%)']


def main():
    (HERE / 'tables').mkdir(exist_ok=True)
    (HERE / 'figures').mkdir(exist_ok=True)
    summary = pd.read_csv(RUN / 'scenario_summary.csv').query('n == 1000').set_index('scenario')
    thresholds = pd.read_csv(RUN / 'threshold_summary.csv')
    alerts = thresholds.query('n == 1000 and threshold == 0.3').set_index('scenario')
    lines = [r'\begin{table}[t]',
             r'\caption{Fixed-model results for 1,000-row windows: mean$\pm$sample SD over five seeds. Alerts use $\tau_D=0.30$; S0 alert count uses all 30 stable windows.}',
             r'\label{tab:results}', r'\centering', r'\small',
             r'\begin{tabular*}{\linewidth}{@{\extracolsep{\fill}}lcccc@{}}',
             r'\toprule', r'Scenario & Drift share & Macro-F1 & Attack recall & Alerts \\', r'\midrule']
    for key, label in zip(SCENARIOS, LABELS):
        row = summary.loc[key]
        cells = [f'{row[m]:.3f}$\\pm${row[s]:.3f}' for m, s in
                 [('drift_mean', 'drift_std'), ('macro_f1_mean', 'macro_f1_std'), ('recall_mean', 'recall_std')]]
        a = alerts.loc[key]
        lines.append(' & '.join([label] + cells + [f'{int(a.alerts_bh)}/{int(a.windows)}']) + r' \\')
    lines += [r'\bottomrule', r'\end{tabular*}', r'\end{table}']
    (HERE / 'tables/drift_main.tex').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    plt.rcParams.update({'font.size': 11, 'pdf.fonttype': 42})
    fig, axes = plt.subplots(1, 2, figsize=(6.6, 2.65), layout='constrained', sharey=True)
    for ax, n in zip(axes, [500, 1000]):
        values = thresholds[thresholds.n == n].pivot(index='scenario', columns='threshold', values='alert_rate_bh').loc[SCENARIOS]
        ax.imshow(values.to_numpy(), vmin=0, vmax=1, cmap='Blues', aspect='auto')
        ax.set_xticks(range(4), ['0.10', '0.30', '0.50', '0.70'])
        ax.set_yticks(range(7), ['S0', 'S1: 15%', 'S1: 50%', 'S1: 85%', 'S2: 25%', 'S2: 50%', 'S2: 100%'])
        ax.tick_params(length=0)
        ax.set_title(f'n = {n}', fontsize=11)
        ax.set_xlabel('Drift-share threshold', fontsize=10)
        for i in range(7):
            for j in range(4):
                v = values.iloc[i, j]
                ax.text(j, i, f'{v:.0%}', ha='center', va='center', fontsize=10, color='white' if v > .6 else 'black')
    fig.savefig(HERE / 'figures/threshold_sensitivity.pdf')
    fig.savefig(HERE / 'figures/threshold_sensitivity.png', dpi=180)
    plt.close(fig)
    print('Generated table and publication-sized sensitivity figure from frozen CSVs.')


if __name__ == '__main__':
    main()
