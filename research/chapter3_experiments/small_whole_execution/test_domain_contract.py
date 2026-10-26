"""Pure K195 catalog/metadata fixtures; no build_model, native call or heat."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

HERE = Path(__file__).resolve().parent
PRODUCTION = HERE.parent
sys.path[:0] = [str(HERE), str(PRODUCTION)]
import domain_contract as dc


class DomainContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.instance = json.loads((PRODUCTION / 'results/small_full_chain_precheck02/restricted_input.json').read_text(encoding='utf-8'))
        cls.config = json.loads((PRODUCTION / 'results/whole_long_budget01/method/input_config.json').read_text(encoding='utf-8'))
        cls.manifest = [json.loads(line) for line in
            (PRODUCTION / 'results/small_exact_protocol01/scene_manifest.jsonl').read_text(encoding='utf-8').splitlines()]

    def model(self):
        _, options, _ = dc.retained_catalog(self.instance, self.config)
        return SimpleNamespace(instance=deepcopy(self.instance), options=deepcopy(options),
            option_vars=list(range(72)), integer=list(range(72)), logical_binary=list(range(75)),
            names=['y:' + row['option_id'] for row in options] + ['x:fake', 'rho:fake', 'w:fake'],
            lb=[0.0] * 75, ub=[1.0] * 75,
            formulation=dict(fix_late_options=True, aggregate_opp_locks=True,
                relax_auxiliary_integrality=True, energy_lower_bounds=True,
                prefilter_deadlines=True, idle_policy='auto_low_immediate_v1',
                fixed_deployment=False, fixed_scene_id=None),
            preprocessing=dict(options_before_deadline_filter=78, deadline_removed_count=6,
                empty_stage_option_sets=[], fixed_deployment=None, fixed_scene_id=None),
            scenes={s['id']: dict(theta=[[0]], energy=[0]) for s in self.instance['scenarios']})

    def complete_candidate(self):
        rows = {}
        for sid in ('AB_offset_0ms', 'AC_offset_0ms'):
            entry = next(e for e in self.manifest if e['scene_id'] == sid and e['shared_A_device'] == 'NPU0')
            rows[sid] = deepcopy(entry['candidate']['scenes'][sid])
        return {'scenes': rows}

    def test_static_manifest_all_1550(self):
        self.assertEqual(dc.audit_static(self.instance, self.config, self.manifest)['compatible_joint_arrangements'], 274500)

    def test_six_removals_only_deadline_impossible(self):
        raw, kept, removed = dc.retained_catalog(self.instance, self.config)
        self.assertEqual((len(raw), len(kept), len(removed)), (78, 72, 6))
        self.assertTrue(all(dc.Q(o['end_ms']) > dc.Q(o['request_deadline_ms']) for o in removed))

    def test_complete_member_without_physics(self):
        self.assertEqual(dc.validate_candidate(self.instance, self.complete_candidate(), self.config)['stage_choices'], 12)

    def test_missing_scene_rejected(self):
        candidate = self.complete_candidate(); candidate['scenes'].pop('AC_offset_0ms')
        with self.assertRaises(ValueError): dc.validate_candidate(self.instance, candidate, self.config)

    def test_nonmember_start_rejected(self):
        candidate = self.complete_candidate(); candidate['scenes']['AB_offset_0ms'][0]['start_ms'] = '399'
        with self.assertRaises(ValueError): dc.validate_candidate(self.instance, candidate, self.config)

    def test_shared_device_mismatch_rejected(self):
        candidate = self.complete_candidate()
        entry = next(e for e in self.manifest if e['scene_id'] == 'AC_offset_0ms' and e['shared_A_device'] == 'CPU1')
        candidate['scenes']['AC_offset_0ms'] = deepcopy(entry['candidate']['scenes']['AC_offset_0ms'])
        with self.assertRaises(ValueError): dc.validate_candidate(self.instance, candidate, self.config)

    def test_metadata_fake_passes(self):
        self.assertEqual(dc.validate_model(self.model(), self.instance, self.config)['stage_integer_options'], 72)

    def test_integer_omission_rejected(self):
        model = self.model(); model.integer.pop()
        with self.assertRaises(ValueError): dc.validate_model(model, self.instance, self.config)

    def test_auxiliary_integer_rejected(self):
        model = self.model(); model.integer.append(72)
        with self.assertRaises(ValueError): dc.validate_model(model, self.instance, self.config)

    def test_nonbinary_bound_rejected(self):
        model = self.model(); model.ub[0] = 0.5
        with self.assertRaises(ValueError): dc.validate_model(model, self.instance, self.config)

    def test_option_reordering_rejected(self):
        model = self.model(); model.options.reverse()
        with self.assertRaises(ValueError): dc.validate_model(model, self.instance, self.config)

    def test_fixed_deployment_rejected(self):
        model = self.model(); model.formulation['fixed_deployment'] = True
        with self.assertRaises(ValueError): dc.validate_model(model, self.instance, self.config)

    def test_neighborhood_rejected(self):
        model = self.model(); model.neighborhood_condition = {'protocol': 'any'}
        with self.assertRaises(ValueError): dc.validate_model(model, self.instance, self.config)

    def test_physics_absent_rejected(self):
        model = self.model(); next(iter(model.scenes.values()))['theta'] = []
        with self.assertRaises(ValueError): dc.validate_model(model, self.instance, self.config)

    def test_manifest_duplicate_rejected(self):
        manifest = deepcopy(self.manifest); manifest[1] = deepcopy(manifest[0]); manifest[1]['ordinal'] = 2
        with self.assertRaises(ValueError): dc.audit_static(self.instance, self.config, manifest)

    def test_manifest_bad_id_rejected(self):
        manifest = deepcopy(self.manifest); manifest[0]['id'] = '0' * 64
        with self.assertRaises(ValueError): dc.audit_static(self.instance, self.config, manifest)


if __name__ == '__main__':
    unittest.main(verbosity=2)
