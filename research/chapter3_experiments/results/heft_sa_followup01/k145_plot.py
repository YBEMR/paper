"""Plot archived upper/lower bound events; no search or physical evaluation."""
from pathlib import Path
import csv
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

here = Path(__file__).resolve().parent
analysis = json.loads((here/'k145_analysis.json').read_text(encoding='utf-8'))
with (here/'k145_progress.csv').open(encoding='utf-8-sig', newline='') as stream:
    events = list(csv.DictReader(stream))
fig, ax = plt.subplots(figsize=(7.4, 4.2), layout='constrained')
for name, color in [('heft', '#2468a2'), ('sa101', '#d87920')]:
    info = next(row for row in analysis['methods'] if row['method'] == name)
    rows = [r for r in events if r['method'] == name]
    times = [float(row['at_s']) for row in rows]
    energy = [float(row['U_J']) for row in rows]
    times.append(info['method_elapsed_s']); energy.append(energy[-1])
    label = 'HEFT' if name == 'heft' else 'SA (seed 101)'
    ax.step(times, energy, where='post', color=color, label=label, linewidth=1.8)
    ax.scatter([times[-1]], [energy[-1]], color=color, s=28, zorder=5)
lower = analysis['methods'][0]['L0_J']
ax.axhline(lower, linestyle='--', color='#555555', label='Independent lower bound L0', linewidth=1.1)
ax.set(xlim=(0, 305), xlabel='Method elapsed time (s)', ylabel='Weighted system energy (J)',
       title='K145: independent HEFT / SA101 calls, 300 s maximum each')
ax.grid(alpha=0.22); ax.legend(fontsize=9)
for ext in ('png', 'svg'):
    target = here/('k145_energy_progress.'+ext)
    fig.savefig(target, dpi=180)
    if ext == 'svg':
        # Matplotlib paths contain redundant line-end spaces; preserve geometry.
        target.write_text('\n'.join(line.rstrip() for line in target.read_text(encoding='utf-8').splitlines())+'\n', encoding='utf-8')
plt.close(fig)
