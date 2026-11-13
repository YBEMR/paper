"""Frozen target/pair/mode/template/ranking order with exact rejection guards."""
from copy import deepcopy
from fractions import Fraction as F
from itertools import product

from .. import graph_core
from ..blocking import core, method as frozen
from .prefilter import RoundFilter, new_counts

ORIGINAL_PACKETS = frozen.candidate_packets


def rejected(sid, selected, orientation, template, certificate, base=None, edge=None):
    packet = core._packet(sid, selected, orientation, template)
    packet.update(reason='PREFILTER_' + certificate['kind'], prefilter_certificate=certificate)
    if edge is not None:
        packet.update(additional_reversed_edges=[list(edge)],
            base_blocking_traces=deepcopy(base['blocking_traces']))
    return packet


def candidate_packets(instance, incumbent, budget, *, diagnostics=None,
                      allow_blocking_edges=True, prefilter_enabled=True, counts=None):
    if type(allow_blocking_edges) is not bool or type(prefilter_enabled) is not bool:
        raise ValueError('boolean switches required')
    if not prefilter_enabled:
        yield from ORIGINAL_PACKETS(instance, incumbent, budget, diagnostics=diagnostics,
                                    allow_blocking_edges=allow_blocking_edges)
        return
    diagnostics = [] if diagnostics is None else diagnostics
    counts = new_counts() if counts is None else counts
    with budget.phase('activity_saving_targets'):
        targets = frozen.energy_targets(instance, incumbent, budget)
    if not targets:
        return
    with budget.phase('resource_association'):
        associations = graph_core.related_pairs(instance, incumbent, budget=budget)
    with budget.phase('structural_prefilter_setup'):
        guard = RoundFilter(instance, incumbent, budget, counts)
        counts['rounds'] += 1
    scenes = {s['id']: s for s in instance['scenarios']}
    emitted = set()
    for target in targets:
        budget.check()
        sid = target['scene_id']
        actions = [a for a in associations if a['scene_id'] == sid and target['stage_id'] in a['stage_ids']]
        if not actions:
            actions = [{'scene_id': sid, 'stage_ids': [target['stage_id']]}]
        rows = {r['stage_id']: r for r in incumbent['scenes'][sid]}
        shared = {s['id']: s['shared_stage_id'] for s in scenes[sid]['stage_instances']}
        for action in actions:
            budget.check()
            selected = action['stage_ids']
            choices = [[target['target_opp']] if iid == target['stage_id'] else
                sorted(m['opp_id'] for m in instance['stage_modes'][shared[iid]]
                       if m['unit_id'] == rows[iid]['unit']) for iid in selected]
            pending, seen = [], set()

            def record(packet, extra):
                budget.check()
                item = {'target': deepcopy(target), 'scene_id': sid,
                    'selected_stages': list(selected), 'opp_overrides': deepcopy(overrides),
                    'orientation': orientation, 'template': template,
                    'extra_resource_edge': None if extra is None else list(extra),
                    'state': packet['state'], 'reason': packet.get('reason'),
                    'deadline_violations': deepcopy(packet.get('deadline_violations', [])),
                    'blocking_traces': deepcopy(packet.get('blocking_traces', [])),
                    'base_blocking_traces': deepcopy(packet.get('base_blocking_traces', [])),
                    'additional_reversed_edges': deepcopy(packet.get('additional_reversed_edges', []))}
                if 'prefilter_certificate' in packet:
                    item['prefilter_certificate'] = deepcopy(packet['prefilter_certificate'])
                diagnostics.append(item)
                if packet['state'] != 'COMPLETE_LEGAL_CANDIDATE':
                    return
                key = frozen.digest(packet['candidate'])
                if key not in seen and key not in emitted:
                    seen.add(key)
                    packet['energy_target'] = deepcopy(target)
                    pending.append(packet)

            for mode_tuple in product(*choices):
                overrides = dict(zip(selected, mode_tuple))
                for orientation in (('incumbent', 'reverse') if len(selected) == 2 else ('incumbent',)):
                    for template in frozen.RULES['templates']:
                        budget.check()
                        with budget.phase('structural_prefilter_check'):
                            bounds, cert = guard.group(sid, selected, overrides, orientation, template)
                        if cert is not None:
                            counts['base_pruned'] += 1; counts['reject_' + cert['kind']] += 1
                            record(rejected(sid, selected, orientation, template, cert), None)
                            continue
                        with budget.phase('blocking_graph_construct'):
                            counts['base_constructed'] += 1
                            packet = core.reconstruct(instance, incumbent, sid, selected, overrides,
                                orientation=orientation, template=template, budget=budget)
                            record(packet, None)
                        for edge in (core.blocking_edges(packet) if allow_blocking_edges else ()):
                            budget.check()
                            with budget.phase('structural_prefilter_check'):
                                cert = guard.edge(bounds, packet, edge)
                            if cert is not None:
                                counts['extra_pruned'] += 1; counts['reject_' + cert['kind']] += 1
                                record(rejected(sid, selected, orientation, template, cert, packet, edge), edge)
                                continue
                            with budget.phase('blocking_graph_construct'):
                                counts['extra_constructed'] += 1
                                repaired = core.reconstruct(instance, incumbent, sid, selected, overrides,
                                    orientation=orientation, template=template,
                                    extra_resource_edge=edge, budget=budget)
                                record(repaired, edge)
            with budget.phase('nonthermal_ranking'):
                pending.sort(key=lambda p: (F(p['nonthermal_energy_J']), frozen.digest(p['candidate'])))
            for packet in pending:
                budget.check()
                emitted.add(frozen.digest(packet['candidate']))
                yield packet
