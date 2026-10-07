"""Independent NumPy/SciPy replay of every claimed feasible MATLAB schedule."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat
from scipy.linalg import expm


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    folder = args.run
    cases = loadmat(folder / 'inputs.mat', simplify_cells=True)['cases']
    data = loadmat(folder / 'results.mat', simplify_cells=True)
    details = data['details']
    rows = list(csv.DictReader((folder / 'summary.csv').open(encoding='utf-8-sig')))
    assert len(rows) == 4 * len(cases) == 132, 'Incomplete batch'
    checks = [(p, [(rows[4*i+j], details[i, j]) for j in range(4)])
              for i, p in enumerate(cases)]
    diagnostic_rows = 0
    if (folder/'diagnostic/results.mat').exists():
        extra = loadmat(folder/'diagnostic/results.mat', simplify_cells=True)
        erows = list(csv.DictReader((folder/'diagnostic/summary.csv').open(encoding='utf-8-sig')))
        indices = np.atleast_1d(extra['indices']).astype(int)-1
        edetails = extra['details']
        if len(indices) == 1:
            edetails = [edetails]
        for idx, row, detail in zip(indices, erows, edetails):
            checks.append((cases[idx], [(row, detail)]))
        diagnostic_rows = len(erows)
    checked = 0
    max_peak_error = 0.0
    max_energy_error = 0.0
    for p, methods in checks:
        c = p['cfg']
        h, n = int(c['H_ms']), int(p['n'])
        idle = np.asarray(p['idle'], float)
        g1, g2, gn = c['g_env']
        g12, g1n, g2n = c['g12'], c['g1N'], c['g2N']
        g = np.array([[g1+g12+g1n, -g12, -g1n],
                      [-g12, g2+g12+g2n, -g2n],
                      [-g1n, -g2n, gn+g1n+g2n]])
        dynamics = -np.linalg.solve(np.diag(c['C']), g)
        transition = expm(dynamics * 0.000005)
        bound = h * idle.sum()
        for modes in p['modes']:
            modes = np.atleast_2d(modes)
            bound += np.min((modes[:, 3]-idle[modes[:, 0].astype(int)-1])*modes[:, 2])
        assert abs(bound-p['energyLB']) < 1e-8
        for row, detail in methods:
            assert row['case_id'] == p['id']
            if row['status'] not in ('feasible', 'certified_optimal'):
                assert not np.isfinite(float(row['energy_mJ']))
                continue
            placements = detail['placements'] if isinstance(detail, dict) else detail.placements
            v = np.atleast_2d(placements)
            assert v.shape == (n, 7)
            v = v[np.argsort(v[:, 0])]
            assert np.array_equal(v[:, 0], np.arange(1, n+1))
            start = v[:, 5].astype(int)
            assert np.array_equal(start, v[:, 5])
            finish = start + v[:, 3].astype(int)
            assert np.all(start >= p['release'])
            assert np.all(finish <= p['deadline']) and np.all(finish <= h)
            for u, w in np.atleast_2d(p['edges']).astype(int):
                assert finish[u-1] <= start[w-1]
            occupied = np.zeros((h, 3), bool)
            power = np.tile(idle, (h, 1))
            for k in range(n):
                modes = np.atleast_2d(p['modes'][k])
                assert np.any(np.all(np.isclose(modes, v[k, 1:5]), axis=1))
                resource = int(v[k, 1])-1
                assert not occupied[start[k]:finish[k], resource].any()
                occupied[start[k]:finish[k], resource] = True
                power[start[k]:finish[k], resource] = v[k, 4]
            energy = power.sum()  # W*ms = mJ
            state = np.full(3, c['T0']-c['T_amb'])
            peak = float(c['T0'])
            for q in power:
                steady = np.linalg.solve(g, q)
                for _ in range(200):
                    state = steady + transition @ (state-steady)
                    peak = max(peak, state.max()+c['T_amb'])
            assert peak <= c['T_lim']+1e-7
            max_peak_error = max(max_peak_error, abs(peak-float(row['peak'])))
            max_energy_error = max(max_energy_error, abs(energy-float(row['energy_mJ'])))
            assert abs(energy-float(row['energy_mJ'])) < 1e-7
            assert abs(peak-float(row['peak'])) < 1e-6
            assert float(row['lower_mJ']) <= energy+1e-5
            if row['status'] == 'certified_optimal':
                assert abs(energy-float(row['lower_mJ'])) < 1e-5
            checked += 1
    report = dict(status='PASS', cases=len(cases), rows=len(rows),
                  diagnostic_rows=diagnostic_rows,
                  feasible_schedules_checked=checked,
                  max_energy_error_mJ=max_energy_error,
                  max_peak_error_C=max_peak_error,
                  sample_ms=0.005,
                  source_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in sorted((folder/'source').glob('*.m'))})
    (folder/'independent_verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='source_sha256'}, indent=2))


if __name__ == '__main__':
    main()
