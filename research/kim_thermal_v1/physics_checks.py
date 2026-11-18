"""Independent pre-experiment regression against the archived interval evaluator."""
import json
from pathlib import Path
import sys

import numpy as np


from physics import compile_template, expand_segment

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / 'chapter3_experiments'
sys.path.insert(0, str(OLD))
from thermal import Budget, evaluate_piecewise

PLATFORM = json.loads((OLD/'config_v01.json').read_text(encoding='utf-8'))['platform']


def block(start, end, opp, activity):
    return expand_segment(PLATFORM, dict(start_ms=start, end_ms=end, opp=opp, activity_W=activity))


def oracle(segments, initial, limits):
    report = evaluate_piecewise(PLATFORM, initial, limits, segments, segments[-1]['end_ms'],
                                budget=Budget(seconds=70))
    assert report['complete'], report['reason']
    return report


def checks():
    T0 = [52, 47, 44, 40]
    limits = [80]*4
    segments = [block(0, 30, 'LHL', [0.5,0,1.7,0]), block(30, 80, 'HLH', [0,1.25,0,1.2]),
                block(80, 110, 'LLL', [0,0,0,0])]
    tpl = compile_template(PLATFORM, segments)
    replay = tpl.step(T0, limits, detail=True)
    ref = oracle(segments, T0, limits)
    assert replay['safe'] and ref['state'] == 'SAFE'
    nodes = PLATFORM['node_order']
    # Legacy directed decimal intervals can be much narrower than binary64.
    tolerance = 1e-10
    for i,node in enumerate(nodes):
        lo, hi = map(float, ref['final_temperature_degC'][node])
        assert lo-tolerance <= replay['final_T'][i] <= hi+tolerance
        lo, hi = map(float, ref['peaks_degC'][node])
        assert lo <= replay['peak_upper'][i] and hi >= replay['peak_lower'][i]
    lo, hi = map(float, ref['energy_J'])
    assert lo-tolerance <= replay['energy_J'] <= hi+tolerance
    step1 = compile_template(PLATFORM, segments[:1]).step(T0)
    step2 = compile_template(PLATFORM, segments[1:]).step(step1['final_T'])
    assert np.allclose(replay['final_T'], step2['final_T'], atol=tolerance, rtol=0)
    assert abs(replay['energy_J']-step1['energy_J']-step2['energy_J']) < tolerance
    assert abs(sum(row['energy_J'] for row in replay['trace']) - replay['energy_J']) < tolerance
    pulse = [block(0, 4000, 'LLL', [0,0,0,0])]
    initial = [40,80,85,80]
    node_limits = [41,95,95,95]
    # Single constant-power interval. Both endpoints pass, first CPU heats
    # then cools under lateral conduction. No subtask edge at the peak.
    trapped = compile_template(PLATFORM, pulse).step(initial,node_limits,True)
    other = oracle(pulse, initial, node_limits)
    assert all(x < y and z < y for x,y,z in zip(initial,node_limits,trapped['final_T']))
    assert not trapped['safe'] and trapped['peak_lower'][0] > 41
    assert other['state'] == 'THERMAL_VIOLATION'
    old_peak = list(map(float,other['peaks_degC']['CPU1']))
    assert old_peak[0] <= trapped['peak_upper'][0] and old_peak[1] >= trapped['peak_lower'][0]
    return {'tests_passed':['continuous energy integral vs archived decimal interval kernel',
        'all-node final temperatures vs archived interval kernel',
        'continuous peaks vs archived interval kernel','segment integral sums',
        'split/rejoin propagation and energy','interior violation with safe endpoints',
        'legacy interior-peak temperature agreement'],
        'oracle_energy_interval_J': ref['energy_J'], 'archive_final_T_C': ref['final_temperature_degC'],
        'new_energy_J':replay['energy_J'],'new_final_T_C':replay['final_T'],
        'hidden_peak_test':{'first_CPU_start_C':40,'first_CPU_end_C':trapped['final_T'][0],
                            'limit_C':41,'new_peak_C':[trapped['peak_lower'][0],trapped['peak_upper'][0]],
                            'old_peak_C':other['peaks_degC']['CPU1']}}


if __name__ == '__main__':
    print(json.dumps(checks(), ensure_ascii=False, indent=2))

