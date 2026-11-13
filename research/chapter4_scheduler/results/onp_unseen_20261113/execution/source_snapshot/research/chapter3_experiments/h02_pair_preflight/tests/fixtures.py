"""Synthetic payloads only: no scheduling, physical evaluation or real SAFE."""
from fractions import Fraction
from h02_pair_preflight.common import POLICY, sha


def candidate_for(instance, offset=0):
    """CPU1/H literal rows; their temporal legality is deliberately not claimed."""
    return {'scenes': {scene['id']: [
        {'stage_id': stage['id'], 'unit': 'CPU1', 'opp': 'H',
         'start_ms': str(Fraction(offset) + 20 * i)}
        for i, stage in enumerate(scene['stage_instances'])]
        for scene in instance['scenarios']}}


def mock_legal_receipt(instance):
    return {'state': 'SCHEDULE_VALID_THERMAL_UNCHECKED',
            'scenes': {scene['id']: {'mock_only': True} for scene in instance['scenarios']},
            'evidence_kind': 'MOCK_ONLY'}


def mock_safe_receipt(instance, candidate, accuracy, energy='1', formed=1.0):
    """Invented exact receipts for contract tests, never scientific evidence."""
    total = Fraction(energy)
    external = Fraction(instance['platform']['external_common_power_W']) * Fraction(instance['window_ms']) / 1000
    baseline = total - Fraction('0.2') - Fraction('0.18') - external
    point = lambda x: [str(x), str(x)]
    scenes = {}
    for scene in instance['scenarios']:
        nodes = instance['platform']['node_order']
        scenes[scene['id']] = {
            'state': 'SAFE', 'complete': True, 'rankable_energy': True,
            'energy_accuracy_met': True,
            'covered_until_s': str(Fraction(instance['window_ms']) / 1000),
            'energy_J': point(total),
            'energy_components_J': {
                'baseline': point(baseline), 'activity': point(Fraction('0.2')),
                'temperature_correction': point(Fraction('0.18')),
                'external_common': point(external)},
            'peaks_degC': {node: ['50', '50'] for node in nodes},
            'minimum_degC': {node: ['50', '50'] for node in nodes}}
    weighted = sum(Fraction(scene['weight']) * total for scene in instance['scenarios'])
    return {
        'state': 'SAFE', 'reason': 'MOCK_COMPLETED', 'problem_id': instance['id'],
        'rankable_energy': True, 'completed_at_elapsed_s': formed,
        'violations': [], 'scenes': scenes,
        'weighted_energy_J': point(weighted), 'safe_upper_bound_J': str(weighted),
        'control_policy': {'idle_policy': POLICY, 'idle_delay_ms': '0'},
        'numerical_protocol': 'directed-decimal60-taylor18-scaled100-v1',
        'evidence_identity': {'input_sha256': sha(instance), 'candidate_sha256': sha(candidate)},
        'legality': mock_legal_receipt(instance),
        'evidence_kind': 'MOCK_ONLY', 'formal_experiment_result': False}
