"""Plot archived receipts only; no experiment, candidate or bound calculation."""
import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def plot(folder):
    folder = Path(folder)
    summary = json.loads((folder/'diagnostic_summary.json').read_text(encoding='utf-8'))
    with (folder/'timeline.csv').open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    safe, bounds = [], []
    for row in rows:
        stamp = row.get('method_elapsed_s')
        if not stamp:
            continue
        if row.get('safe_U_J'):
            safe.append((float(stamp), float(row['safe_U_J'])))
        value = row.get('solver_lowerbound_J')
        if value and value not in ('[]', 'None'):
            bounds.append((float(stamp), float(value)))
    fig, ax = plt.subplots(figsize=(7, 3.8), layout='constrained')
    end = summary['limit_s']
    if safe:
        safe.sort()
        best = []
        for stamp, energy in safe:
            best.append((stamp, min(energy, best[-1][1]) if best else energy))
        best.append((end, best[-1][1]))
        ax.step(*zip(*best), where='post', label='Independently SAFE upper bound', color='#176F58')
        ax.scatter(*zip(*safe), color='#176F58', s=18, zorder=3)
    if bounds:
        bounds.sort()
        bounds.append((end, bounds[-1][1]))
        ax.step(*zip(*bounds), where='post', linestyle='--', color='#A65B20',
                label='Solver-reported lower bound')
    ax.set(xlim=(0, end), xlabel='Method wall time (s)', ylabel='System energy (J)',
           title='One warm-start diagnostic; 900 s total budget')
    ax.grid(alpha=.2)
    ax.legend(loc='best', fontsize=9)
    fig.savefig(folder/'progress.png', dpi=180)
    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result-dir', type=Path, required=True)
    plot(parser.parse_args().result_dir)
