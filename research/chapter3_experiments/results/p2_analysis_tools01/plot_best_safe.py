"""Separate postprocessed running-minimum figure; preserve original SAFE plot."""
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parent
FACTS = RESULTS/'p2_execution01/analysis01/facts.json'
OUT = FACTS.parent/'best_safe_upper_bound.png'


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def run():
    if OUT.exists(): raise FileExistsError('Do not overwrite a saved figure')
    facts = json.loads(FACTS.read_text(encoding='utf-8'))
    original = FACTS.parent/'safe_energy_and_independent_bound.png'
    original_before = sha(original); facts_before = sha(FACTS)
    for row in facts['rows']:
        values = [F(v['safe_upper_bound_J']) for v in row['safe_curve'] if v.get('safe_upper_bound_J') is not None]
        final = F(row['usable_U_exact_J']) if row['usable_U_exact_J'] is not None else None
        if (min(values) if values else None) != final:
            raise ValueError('Stored SAFE running minimum does not match original final U')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    for family in ('Microsoft YaHei', 'SimHei', 'Noto Sans CJK SC'):
        try:
            font_manager.findfont(font_manager.FontProperties(family=family), fallback_to_default=False)
            plt.rcParams['font.family'] = family
            break
        except ValueError: pass
    plt.rcParams['axes.unicode_minus'] = False
    colors = {'whole_milp': '#555555', 'anchor_linked4': '#1f77b4', 'heft': '#ff7f0e',
        'sa101': '#2ca02c', 'sa102': '#9467bd', 'sa103': '#8c564b', 'sa104': '#e377c2', 'sa105': '#17becf'}
    names = {'whole_milp': '整体MILP', 'anchor_linked4': '联动MILP', 'heft': 'HEFT',
             **{'sa'+str(i): 'SA'+str(i) for i in range(101, 106)}}
    fig, axes = plt.subplots(1, 5, figsize=(17, 3.9), constrained_layout=True)
    fig.suptitle('已知完整安全见证的运行最小上界', fontsize=13)
    for ax, cohort in zip(axes, facts['cohorts']):
        rows = [r for r in facts['rows'] if r['problem_id'] == cohort['problem_id']]
        for row in rows:
            running = []; best = None
            for value in sorted(row['safe_curve'], key=lambda v: v.get('completed_at_s', float('inf'))):
                t = value.get('completed_at_s'); u = value.get('safe_upper_bound_J')
                if t is None or u is None or t >= 300: continue
                u = F(u); best = u if best is None else min(best, u)
                running.append((t, float(best)))
            if running:
                t, u = map(list, zip(*running)); stop = min(300, row['method_root_s'] or t[-1])
                ax.step(t+[max(t[-1], stop)], u+[u[-1]], where='post', label=names[row['method']],
                        color=colors[row['method']], linewidth=1.25, alpha=.9)
        for i, lower in enumerate(sorted({r['certified_L0_J'] for r in rows if r['certified_L0_J'] is not None})):
            ax.axhline(lower, color='black', ls='--', linewidth=.8, label='独立L0' if i == 0 else None)
        ax.set(title=cohort['problem_id'].split('__')[-1], xlabel='方法时间（s）', ylabel='完整窗口能量（J）', xlim=(0, 300))
        ax.grid(alpha=.2)
    legend = {}
    for ax in axes:
        handles, labels = ax.get_legend_handles_labels(); legend.update(zip(labels, handles))
    fig.legend(list(legend.values()), list(legend), loc='lower center', bbox_to_anchor=(.5, -.055), ncol=9, fontsize=8)
    fig.savefig(OUT, dpi=180, bbox_inches='tight'); plt.close(fig)
    if sha(FACTS) != facts_before or sha(original) != original_before:
        raise ValueError('Original data or figure changed')
    report = {'passed': True, 'curves': len(facts['rows']), 'final_U_exact_matches': len(facts['rows']),
        'title': '已知完整安全见证的运行最小上界', 'facts_sha256': facts_before,
        'original_figure_sha256': original_before, 'original_figure_unchanged': True,
        'new_figure_sha256': sha(OUT), 'script_sha256': sha(Path(__file__)),
        'new_scientific_evaluations': 0, 'new_U_or_candidate': False,
        'interpretation': 'Postprocessed running minimum of saved complete SAFE receipts; SAFE evaluations are not formal algorithm update events.'}
    with (HERE/'best_safe_plot_review.json').open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2); stream.write('\n')
    return report


if __name__ == '__main__':
    print(run())
