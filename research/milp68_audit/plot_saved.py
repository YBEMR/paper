"""Plot saved traces; no reevaluation or search."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root = Path(__file__).resolve().parents[2]
out = root/'research/matlab_config_value_src/milp68_reports/frozen_20260927_113720_286'
records = json.loads((out/'saved_diagnostics.json').read_text(encoding='utf-8'))
plt.rcParams.update({'font.size': 10})
for i in range(10):
    pair = records[i*2:i*2+2]
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2), constrained_layout=True)
    xmax = max(r['elapsed_s'] for r in pair)*1.08
    for j, r in enumerate(pair):
        b = np.array(r['bound_trace'], dtype=float)
        colour = ['#1764a0', '#c85016'][j]
        mask = np.isfinite(b[:, 2])
        ax[0].plot(b[mask, 0], b[mask, 2]/16, '-o', color=colour, ms=5,
                   label=r['method'])
        ax[1].step(b[:, 0], np.where(np.isfinite(b[:,1]), b[:,1]/16, np.nan),
                   where='post', color=colour, label=['search certified bound', 'MILP independent L0'][j])
        if j==1:
            t=np.array(r['solver_trace'], dtype=float)
            if len(t):
                m=np.isfinite(t[:,2])
                ax[1].plot(t[m,0], t[m,2]/16, ':D', color='#7a4594', ms=4,
                           label='MILP reported (not certified)')
    if not np.isfinite(pair[0]['upper_J']) and not np.isfinite(pair[1]['upper_J']):
        ax[0].text(.5,.5,'No safe witness\nSearch: proved grid infeasible\nMILP: reported infeasible',
                   ha='center', va='center', transform=ax[0].transAxes)
    for a in ax:
        a.set_xlim(0,xmax);a.set_xlabel('Elapsed time / s');a.set_ylabel('System energy / mJ')
        a.grid(alpha=.2);a.legend(fontsize=8)
    ax[0].set_title('Verified safe upper bounds (markers = evidence)')
    ax[1].set_title('Certified and solver-reported bounds')
    fig.suptitle(pair[0]['input_id'])
    fig.savefig(out/f'figure_{i+1:02d}.png', dpi=180)
    plt.close(fig)
