"""Small, explicitly synthetic mechanism screen. Python + numpy + scipy only."""
import csv
import hashlib
import itertools
import json
import pathlib
import platform
import subprocess
import time
from collections import defaultdict

import numpy as np
import scipy
from scipy.integrate import solve_ivp
from scipy.linalg import expm

ROOT = pathlib.Path(__file__).resolve().parent
P = json.loads((ROOT / 'parameters.json').read_text(encoding='utf-8'))
C = np.array(P['C_J_per_K'])
g = P['G_coupling_W_per_K']
G = np.diag(P['G_environment_W_per_K']) + np.array([[g, -g], [-g, g]])
L = np.array(P['leak_at_40C_W'])
BASE = np.array(P['awake_base_W'])
SLEEP = np.array(P['sleep_base_W'])
H = P['main_horizon_s']
TA = P['ambient_C']
BETA = P['leak_beta_per_K']
TIE = P['numerics']['energy_tie_J']
assert np.linalg.eigvalsh(G).min() > 0 and min(C) > 0


def segment(start, end, dynamic=(0., 0.), awake=(1., 1.), switch=(0., 0.)):
    return dict(start=float(start), end=float(end), dynamic=list(dynamic), awake=list(awake), switch=list(switch))


def a_actions():
    for mapping in itertools.product(range(2), repeat=2):
        for first in range(2):
            for k, offset in enumerate(P['A']['offsets_s']):
                yield dict(direction='A', id=f'A-{mapping[0]}{mapping[1]}-{first}-{k}', mapping=mapping, first=first, offset=offset)


def a_schedule(a, variant):
    cfg = P['A']
    m, first = a['mapping'], a['first']
    second = 1 - first
    d = [cfg['task_X_solo_duration_s'][m[0]], cfg['task_Y_solo_duration_s'][m[1]]]
    q = [cfg['task_X_dynamic_W'][m[0]], cfg['task_Y_dynamic_W'][m[1]]]
    rate = 1. if variant == 'no_interference' else cfg['cross_device_overlap_progress_rate']
    offset = a['offset']
    intervals = []
    starts, ends = [0., 0.], [0., 0.]
    starts[first] = 0.
    if m[0] == m[1] or offset >= d[first]:
        starts[second] = max(offset, d[first]) if m[0] == m[1] else offset
        ends[first], ends[second] = d[first], starts[second] + d[second]
    else:
        starts[second] = offset
        remaining = [d[i] - offset if i == first else d[i] for i in range(2)]
        ov = min(remaining) / rate
        for i in range(2):
            ends[i] = offset + ov + max(0., remaining[i] - ov * rate)
    events = sorted(set([0., H] + starts + ends))
    overlap = max(0., min(ends) - max(starts)) if m[0] != m[1] else 0.
    recovered_work = [0., 0.]
    for s, e in zip(events, events[1:]):
        mid = (s + e) / 2
        running = [i for i in range(2) if starts[i] <= mid < ends[i]]
        assert len(running) < 2 or m[0] != m[1]
        dyn = np.zeros(2)
        for i in running:
            dyn[m[i]] += q[i]
            recovered_work[i] += (e-s) * (rate if len(running) == 2 else 1.)
        if len(running) == 2 and variant != 'no_interference':
            dyn += cfg['overlap_extra_W_per_node']
        intervals.append(segment(s, e, dyn))
    assert np.allclose(recovered_work, d, rtol=0, atol=1e-12)
    return intervals, dict(completion_s=max(ends), finish_each_s=ends, overlap_s=overlap,
                           deadline_ok=max(ends) <= cfg['deadline_s'] + 1e-12,
                           structure=f"map={m};first={first};offset={offset:g}")


def compositions(n):
    if n == 0:
        yield ()
    for b in P['B']['batch_sizes']:
        if b <= n:
            for rest in compositions(n-b):
                yield (b,) + rest


def b_actions():
    for comp in compositions(len(P['B']['arrivals_s'])):
        for waits in itertools.product(P['B']['extra_wait_s'], repeat=len(comp)):
            yield dict(direction='B', id='B-'+''.join(map(str, comp))+'-'+''.join('1' if w else '0' for w in waits), batches=comp, waits=waits)


def b_schedule(a, variant):
    cfg = P['B']
    arrivals = cfg['arrivals_s']
    previous = 0.
    done = 0
    intervals = []
    finishes = []
    batch_starts = []
    sleep_on = variant != 'no_sleep'
    for b, wait in zip(a['batches'], a['waits']):
        ready = max(previous, arrivals[done+b-1]) + wait
        sleeping = sleep_on and ready - previous >= P['sleep_gap_min_s'] - 1e-12
        if ready > previous:
            intervals.append(segment(previous, ready, awake=(1, 0 if sleeping else 1)))
        begin = ready
        if sleeping:
            begin += P['wake_duration_s']
            intervals.append(segment(ready, begin, switch=(0, P['wake_extra_energy_J']/P['wake_duration_s'])))
        duration = b * cfg['batch_duration_s']['1'] if variant == 'no_batch_efficiency' else cfg['batch_duration_s'][str(b)]
        power = cfg['batch_dynamic_W']['1'] if variant == 'no_batch_efficiency' else cfg['batch_dynamic_W'][str(b)]
        end = begin + duration
        intervals.append(segment(begin, end, dynamic=(0, power)))
        finishes += [end] * b
        batch_starts.append(begin)
        done += b
        previous = end
    assert done == len(arrivals) and previous <= H + 1e-12
    if previous < H:
        sleeping = sleep_on and H - previous >= P['sleep_gap_min_s'] - 1e-12
        intervals.append(segment(previous, H, awake=(1, 0 if sleeping else 1)))
    return intervals, dict(completion_s=previous, finish_each_s=finishes, overlap_s=0., batch_starts_s=batch_starts,
        deadline_ok=all(f <= r + cfg['relative_deadline_s'] + 1e-12 for f, r in zip(finishes, arrivals)),
        structure=f"batches={a['batches']};waits={a['waits']}")


def schedule(action, variant):
    return a_schedule(action, variant) if action['direction'] == 'A' else b_schedule(action, variant)


def rates(s, T, variant):
    awake = np.array(s['awake'])
    base = SLEEP + (BASE - SLEEP) * awake
    gating = P['sleep_leak_factor'] + (1-P['sleep_leak_factor']) * awake
    if variant == 'constant_leak':
        leak = L * gating
    elif variant == 'affine_control':
        leak = L * (1 + BETA * (T-40)) * gating
    else:
        leak = L * np.exp(BETA * (T-40)) * gating
    assert np.all(leak >= 0)
    dyn, sw = np.array(s['dynamic']), np.array(s['switch'])
    heat = base + dyn + sw + leak
    energy = np.array([base.sum()+P['external_base_W'], dyn.sum(), leak.sum(), sw.sum()])
    return heat, energy


def evaluate(action, variant, initial, tight=False, continuation=False):
    segs, meta = schedule(action, variant)
    y = np.r_[initial, np.zeros(5)]  # T0,T1; base,dynamic,leak,switch,total
    peak = np.array(initial, dtype=float)
    max_balance_error = 0.
    for s in segs:
        def rhs(t, z):
            heat, energy = rates(s, z[:2], variant)
            return np.r_[(-G @ (z[:2]-TA)+heat)/C, energy, energy.sum()]
        sol = solve_ivp(rhs, (s['start'], s['end']), y, method='DOP853',
            rtol=1e-11 if tight else P['numerics']['rtol'], atol=1e-13 if tight else P['numerics']['atol'],
            max_step=.005 if tight else .01, dense_output=True)
        assert sol.success
        samples = np.linspace(s['start'], s['end'], max(2, int(np.ceil((s['end']-s['start'])/(.0005 if tight else .001)))+1))
        peak = np.maximum(peak, sol.sol(samples)[:2].max(axis=1))
        y = sol.y[:, -1]
        max_balance_error = max(max_balance_error, abs(y[2:6].sum()-y[6]))
    main_y = y.copy()
    if continuation:
        tail = segment(H, H+P['continuation_s'], awake=(1, 1 if action['direction']=='A' or variant=='no_sleep' else 0))
        def rhs_tail(t, z):
            heat, energy = rates(tail, z[:2], variant)
            return np.r_[(-G@(z[:2]-TA)+heat)/C, energy, energy.sum()]
        sol = solve_ivp(rhs_tail, (tail['start'], tail['end']), y, method='DOP853', rtol=1e-10, atol=1e-12, max_step=.1, dense_output=True)
        assert sol.success
        samples = np.arange(H, H+P['continuation_s']+.00001, .05)
        tail_peak = np.maximum(peak, sol.sol(samples)[:2].max(axis=1))
        y = sol.y[:, -1]
        meta.update(extended_energy_J=float(y[6]), extended_peak_C=float(tail_peak.max()), extended_end_C=y[:2].tolist())
    meta.update(energy_J=float(main_y[6]), base_J=float(main_y[2]), dynamic_J=float(main_y[3]), leakage_J=float(main_y[4]), switching_J=float(main_y[5]),
        peak_C=float(peak.max()), peak_each_C=peak.tolist(), terminal_C=main_y[:2].tolist(), numerical_balance_error_J=max_balance_error,
        feasible=bool(meta['deadline_ok'] and peak.max() <= P['temperature_limit_C']-P['numerics']['temperature_tolerance_C']))
    return meta


def affine_exact(action, initial):
    # Independent matrix exponential for the affine, always-awake A control.
    segs, _ = a_schedule(action, 'affine_control')
    z = np.r_[initial, 1., 0.]
    for s in segs:
        M = np.zeros((4,4))
        M[:2,:2] = (-G + np.diag(L*BETA))/C[:,None]
        constant_heat = G @ np.full(2, TA) + BASE + np.array(s['dynamic']) + L*(1-40*BETA)
        M[:2,2] = constant_heat/C
        M[3,:2] = L*BETA
        M[3,2] = (BASE+np.array(s['dynamic'])+L*(1-40*BETA)).sum()+P['external_base_W']
        z = expm(M*(s['end']-s['start'])) @ z
    return z[3]


def best(rows, energy='energy_J', thermal=True):
    valid = [r for r in rows if r['feasible'] if thermal] if thermal else [r for r in rows if r['deadline_ok']]
    if not valid:
        return dict(energy=None, ids=[], structures=[])
    e = min(r[energy] for r in valid)
    winners = [r for r in valid if r[energy] <= e+TIE]
    return dict(energy=e, ids=[r['id'] for r in winners], structures=sorted(set(r['structure'] for r in winners)))


def main():
    start = time.perf_counter()
    output = ROOT/'results'
    output.mkdir(exist_ok=True)
    actions = list(a_actions()) + list(b_actions())
    (output/'actions.json').write_text(json.dumps(actions,indent=2),encoding='utf-8')
    groups = defaultdict(list)
    full = {}
    rows = []
    with (output/'all_candidates.jsonl').open('w', encoding='utf-8') as f:
        for a in actions:
            variants = ['full','constant_leak','affine_control','no_interference'] if a['direction']=='A' else ['full','constant_leak','no_batch_efficiency','no_sleep']
            for state, initial in P['initial_states_C'].items():
                for variant in variants:
                    if time.perf_counter()-start > 120:
                        raise TimeoutError('Predeclared 120s soft cap reached; partial JSONL retained')
                    r = dict(id=a['id'], direction=a['direction'], state=state, variant=variant, **evaluate(a,variant,initial,continuation=variant=='full'))
                    f.write(json.dumps(r)+'\n')
                    f.flush()
                    rows.append(r)
                    groups[a['direction'],state,variant].append(r)
                    if variant=='full': full[a['id'],state]=r
    summaries = []
    for (direction,state,variant), group in groups.items():
        b = best(group)
        replay = [full[i,state] for i in b['ids']]
        safe = [r for r in replay if r['feasible']]
        summaries.append(dict(direction=direction,state=state,variant=variant,candidates=len(group),feasible=sum(r['feasible'] for r in group),
            best=b,replay_full_feasible=len(safe),replay_full_energy_min=min((r['energy_J'] for r in safe),default=None),
            replay_full_energy_max=max((r['energy_J'] for r in safe),default=None),
            best_without_temperature_limit=best(group,thermal=False),
            extended_best=best(group,'extended_energy_J') if variant=='full' else None))
    checks = {}
    a0 = groups['A','cool','affine_control']
    for state in ['warm','cpu_warm']:
        delta = [r['energy_J']-r0['energy_J'] for r,r0 in zip(groups['A',state,'affine_control'],a0)]
        checks['affine_initial_offset_spread_'+state+'_J'] = max(delta)-min(delta)
    checks['affine_expm_max_abs_error_J'] = max(abs(affine_exact(a,P['initial_states_C'][s])-next(r['energy_J'] for r in groups['A',s,'affine_control'] if r['id']==a['id'])) for a in actions if a['direction']=='A' for s in P['initial_states_C'])
    checks['energy_balance_max_error_J'] = max(r['numerical_balance_error_J'] for r in rows)
    selected = set()
    for direction in ['A','B']:
        for state in P['initial_states_C']:
            group = sorted([r for r in groups[direction,state,'full'] if r['feasible']], key=lambda r:r['energy_J'])
            selected.update((r['id'],state) for r in group[:3])
    selected.update((i,state) for i in ['A-10-0-0','A-10-0-3','B-1111-0000','B-22-00'] for state in P['initial_states_C'])
    amap = {a['id']:a for a in actions}
    validation = []
    for aid,state in sorted(selected):
        rerun = evaluate(amap[aid],'full',P['initial_states_C'][state],tight=True)
        old = full[aid,state]
        validation.append(dict(id=aid,state=state,energy_diff_J=rerun['energy_J']-old['energy_J'],peak_diff_C=rerun['peak_C']-old['peak_C']))
    checks['tight_reruns'] = len(validation)
    checks['tight_max_energy_diff_J'] = max(abs(r['energy_diff_J']) for r in validation)
    checks['tight_max_peak_diff_C'] = max(abs(r['peak_diff_C']) for r in validation)
    checks['pass'] = bool(checks['affine_expm_max_abs_error_J']<1e-8 and checks['energy_balance_max_error_J']<1e-8 and checks['tight_max_energy_diff_J']<1e-8 and checks['tight_max_peak_diff_C']<1e-5)
    assert checks['pass']
    env = dict(python=platform.python_version(),numpy=np.__version__,scipy=scipy.__version__,platform=platform.platform(),
        elapsed_s=time.perf_counter()-start,git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        parameters_sha256=hashlib.sha256((ROOT/'parameters.json').read_bytes()).hexdigest(),code_sha256=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest())
    for name,obj in [('summary',summaries),('checks',checks),('tight_validation',validation),('run_environment',env)]:
        (output/(name+'.json')).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
    fields=['id','direction','state','variant','feasible','deadline_ok','energy_J','dynamic_J','leakage_J','base_J','switching_J','completion_s','overlap_s','peak_C','extended_energy_J','structure']
    with (output/'all_candidates.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    print(json.dumps(dict(rows=len(rows),actions=len(actions),checks=checks,environment=env),indent=2))


if __name__=='__main__': main()
