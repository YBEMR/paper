"""Correct component colours without changing the archived numeric analysis."""
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent
facts = json.loads((OUT/'facts.json').read_text(encoding='utf-8'))
jobs = facts['jobs']
fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.4), layout='constrained')
components = [('activity', '#487aa2'), ('baseline', '#df9c4a'),
              ('external_common', '#6c9a70'), ('temperature_correction', '#ba6464')]
for job, color, label in zip(jobs, ('#31658b', '#d37c29'), ('Linked 4-open', 'Linked 5-open')):
    points = job['complete_updates']
    xs = [p['at_s'] for p in points]
    ys = [float(F(p['energy_J'][1])) for p in points]
    axes[0].step(xs+[300], ys+[ys[-1]], where='post', color=color, label=label)
    axes[0].scatter(xs, ys, color=color, s=17)
    phase2 = job['phase_attribution'][1]
    axes[0].axvline(phase2['started_at_s'], color=color, alpha=.55, linestyle='--', linewidth=.8)
    bottom = 0.
    for component, component_color in components:
        bounds = job['components_J'][component]
        value = float((F(bounds[0])+F(bounds[1]))/2)
        axes[1].bar(label, value, bottom=bottom, color=component_color,
                    label=component.replace('_', ' ') if job is jobs[0] else None)
        bottom += value
bounds = [F(j['independent_bounds']['L0']['lower_bound_J']) for j in jobs]
assert bounds[0] == bounds[1]
axes[0].axhline(float(bounds[0]), color='#575757', linestyle=':', label='Independent L0 (both)')
axes[0].set(xlim=(0, 300), xlabel='Full method time (s)', ylabel='Complete SAFE energy U (J)')
axes[0].grid(alpha=.2)
axes[1].set(ylabel='Weighted complete system energy (J)')
for ax in axes:
    ax.legend(fontsize=8)
fig.savefig(OUT/'energy_progress_and_components_v2.png', dpi=170)
fig.savefig(OUT/'energy_progress_and_components_v2.svg')
plt.close(fig)
report = {'change': 'Fixed component colour map shared by both bars; common L0 shown once',
    'old_figure_preserved': True, 'numeric_facts_unchanged': True,
    'facts_sha256': hashlib.sha256((OUT/'facts.json').read_bytes()).hexdigest(),
    'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'new_research_or_heat_calls': 0}
with (OUT/'plot_revision01.json').open('x', encoding='utf-8') as stream:
    json.dump(report, stream, indent=2)
print('Revised figure saved; numeric facts unchanged.')
