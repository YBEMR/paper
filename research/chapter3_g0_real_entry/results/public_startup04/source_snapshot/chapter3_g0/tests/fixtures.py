"""Handmade scheduling fixtures; archived platform bytes are only read.

Durations and activity costs below are artificial unit-test values, never new
formal inputs or measured parameters. No reference schedule is read.
"""
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLATFORM_SOURCE = ROOT / 'chapter3_method_entry_preparation/results/frozen_entry02/common_input.json'


class FakeClock:
    def __init__(self, value=0.0):
        self.value = float(value)

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += float(seconds)


def bundle(n=4, *, scene_ids=('X', 'Y'), copies=1, stagger_ms=0, shape='diamond'):
    original = json.loads(PLATFORM_SOURCE.read_text(encoding='utf-8'))
    config = deepcopy(original['config'])
    instance = deepcopy(original['instance'])
    instance.update(id='MANUAL-G0', condition_id='MANUAL-ONLY', sample_id='HANDMADE',
                    window_ms=str(20*n*copies+int(stagger_ms)+100), start_grid_ms='5')
    instance.pop('start_domain', None)
    instance['status'] = 'MANUAL_FIXTURE_NOT_SCIENTIFIC_INPUT'
    instance['stage_modes'] = {}
    units = {u['id']: u for u in instance['platform']['units']}
    unit_order = ['CPU1', 'CPU2', 'GPU0', 'NPU0']
    for j in range(n):
        shared = f't{j:03d}'
        modes = []
        for uid in unit_order:
            unit = units[uid]
            dom = instance['platform']['domains'][unit['domain_id']]
            for opp, duration, power in [('H',5,8+j), ('M',10,3), ('L',15,1)]:
                physical = dom['opps'][opp]
                modes.append(dict(mode_id=f'{shared}@{uid}:{opp}', shared_stage_id=shared,
                    unit_id=uid, domain_id=unit['domain_id'], power_group_id=unit['power_group_id'],
                    thermal_node_id=unit['thermal_node_id'], opp_id=opp,
                    frequency_GHz=physical['frequency_GHz'], voltage_V=physical['voltage_V'],
                    duration_ms=str(duration), activity_power_W=str(power),
                    activity_energy_J=str(Fraction(duration*power,1000))))
        instance['stage_modes'][shared] = modes
    instance['scenarios'] = []
    candidate = {'scenes': {}}
    for sindex, sid in enumerate(scene_ids):
        scene = deepcopy(original['instance']['scenarios'][0])
        scene.update(id=sid, weight=str(Fraction(1,len(scene_ids))), requests=[],
                     stage_instances=[], dependencies=[])
        candidate['scenes'][sid] = []
        for replica in range(copies):
            rid = f'{sid}.r{replica+1}'
            release = sindex*5 + replica*int(stagger_ms)
            ids = [f'{sid}.r{replica+1}.t{j:03d}' for j in range(n)]
            deadline = int(instance['window_ms'])-5
            scene['requests'].append(dict(id=rid, release_ms=str(release),
                deadline_ms=str(deadline), relative_deadline_ms=str(deadline-release),
                stage_instance_ids=ids))
            for j, iid in enumerate(ids):
                shared = f't{j:03d}'
                scene['stage_instances'].append(dict(id=iid, request_id=rid,
                    shared_stage_id=shared, application='manual-app', legal_units=list(unit_order)))
                candidate['scenes'][sid].append(dict(stage_id=iid, unit=unit_order[j%4],
                    opp='H', start_ms=str(release+replica*n*20+j*20)))
            if shape == 'diamond' and n >= 4:
                edges = [(0,1),(0,2),(1,3),(2,3)] + [(j,j+1) for j in range(3,n-1)]
            elif shape == 'chain' or (shape == 'diamond' and n < 4):
                edges = [(j,j+1) for j in range(n-1)]
            elif shape == 'independent':
                edges = []
            else:
                raise ValueError('unsupported handmade topology')
            scene['dependencies'].extend([[ids[a],ids[b]] for a,b in edges])
        instance['scenarios'].append(scene)
    return config, instance, candidate


def row(candidate, sid, index=0):
    return candidate['scenes'][sid][index]


def set_row(candidate, sid, index, **changes):
    updated = deepcopy(candidate)
    updated['scenes'][sid][index].update(changes)
    return updated
