"""Plot existing complete safe receipts from the stopped prefix only."""
import os
from pathlib import Path
from fractions import Fraction as F
import sys
REPO=next(p for p in Path(__file__).resolve().parents if (p/'AGENTS.md').is_file())
os.environ.setdefault('MPLCONFIGDIR',str(REPO/'.runtime/mpl'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
sys.path.insert(0,str(REPO/'research/chapter3_experiments/p0_execution'))
import batch as b

out=Path(__file__).resolve().parent
review=b.read(out/'review.json');pending=b.read(b.OUT/'ledger.json.pending')
fig,ax=plt.subplots(figsize=(8,4.5))
for row in pending['calls']:
    metrics=row['records']['completion_metrics']
    complete=metrics['complete_SAFE_receipts']
    x=[v['completed_at_s'] for v in complete]
    y=[float(F(v['energy_interval_J'][1])) for v in complete]
    # A valid candidate may be worse; the incumbent bound must never rise.
    y=[min(y[:i+1]) for i in range(len(y))]
    if not x:continue
    x.append(300);y.append(y[-1])
    ax.step(x,y,where='post',label=row['id'])
lower=float(F(review['rows'][0]['independent_L0_J']))
ax.axhline(lower,linestyle='--',color='gray',label='Independent L0 (retrospective reference)')
ax.set(xlabel='Method elapsed time (s)',ylabel='Complete safe energy upper bound (J)',xlim=(0,300),
       title='K155 stopped prefix: R1 only; SA not started')
ax.grid(alpha=.25);ax.legend(fontsize=8)
fig.tight_layout();fig.savefig(out/'safe_energy_prefix.png',dpi=180);plt.close(fig)
print('Saved safe_energy_prefix.png; no new physical evaluation')
