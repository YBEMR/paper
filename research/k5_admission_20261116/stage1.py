"""Exact-arithmetic resource audit; no thermal model, solver or old-code imports."""
from pathlib import Path
from fractions import Fraction as F
from itertools import product
import csv, json, time, hashlib

ROOT = Path(__file__).resolve().parent
MASKS = ((0,), (1,), (2,), (0, 1), (0, 1, 2))
D = ((F('37.52'), F('35.65'), F('35.62')),
     (F('114.55'), F('102.15'), F('100.62')))

def main():
    tic = time.perf_counter()
    rows = []
    for a, b in product(range(5), repeat=2):
        ma, mb = MASKS[a], MASKS[b]
        da, db = D[0][len(ma)-1], D[1][len(mb)-1]
        disjoint = not set(ma).intersection(mb)
        formula = max(da, db) if disjoint else da+db
        # Independently generate earliest event schedules and use bit occupancy.
        bits_a, bits_b = sum(1 << c for c in ma), sum(1 << c for c in mb)
        legal = []
        for sa, sb in ((F(0), F(0)), (F(0), da), (db, F(0))):
            overlaps = max(sa, sb) < min(sa+da, sb+db)
            if overlaps and (bits_a & bits_b):
                continue
            legal.append((max(sa+da, sb+db), sa, sb))
        actual, sa, sb = min(legal)
        assert actual == formula
        rows.append(dict(a_mask=str(ma), b_mask=str(mb), disjoint=disjoint,
                         a_duration_ms=float(da), b_duration_ms=float(db),
                         a_start_ms=float(sa), b_start_ms=float(sb),
                         min_npu_makespan_ms=float(actual),
                         serial_makespan_ms=float(da+db)))
    assert sum(r['disjoint'] for r in rows) == 8
    assert len(rows)-sum(r['disjoint'] for r in rows) == 17
    assert min(r['min_npu_makespan_ms'] for r in rows) == 102.15
    singles = [r for r in rows if r['a_duration_ms'] == 37.52 and r['b_duration_ms'] == 114.55]
    assert len(singles) == 9
    assert min(r['min_npu_makespan_ms'] for r in singles) == 114.55
    thresholds = []
    for job, ds in zip(('A', 'B'), D):
        for small, big in ((1, 2), (2, 3), (1, 3)):
            q = ds[small-1]/ds[big-1]
            thresholds.append(dict(job=job, comparison=f'p{big}/p{small}',
                                   energy_improvement_if_ratio_less_than=str(q), decimal=float(q)))
    out = ROOT/'stage1_results'
    out.mkdir(exist_ok=True)
    with (out/'ordered_masks.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys()); writer.writeheader(); writer.writerows(rows)
    result = dict(status='PASS', ordered_pairs=25, disjoint=8, intersecting=17,
                  all_mask_min_npu_ms=102.15, single_only_min_npu_ms=114.55,
                  energy_thresholds=thresholds, runtime_s=time.perf_counter()-tic,
                  independent_checks='set intersection + analytical makespan vs bit occupancy + event schedules; exact Fraction arithmetic',
                  boundary='NPU makespan after common CPU.pre completion; not measured joint throughput or full-DAG deadline',
                  assumptions=['core1/core2 duration equals core0', 'disjoint masks may execute concurrently',
                               'no concurrent slowdown in stage 1', 'nonpreemptive fixed masks',
                               'pre stages finish together; independent CPU post resources'],
                  source_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (out/'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True))

if __name__ == '__main__':
    main()
