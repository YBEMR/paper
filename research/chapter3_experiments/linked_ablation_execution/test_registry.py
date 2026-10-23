"""Pure frozen-recipe checks; creates no real declaration, claim or method."""
import argparse
from copy import deepcopy
import importlib.abc
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
BLOCKED=[]


class NoScience(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in {'numpy','scipy','matlab','thermal','milp','inputs',
                'schedules','matlab_bridge','linked_method','neighborhood_method'}:
            BLOCKED.append(fullname);raise RuntimeError('Pure registry check blocks science/process imports')
        return None


sys.meta_path.insert(0,NoScience())
def no_process_or_network(event,args):
    if event in {'subprocess.Popen','os.system','os.posix_spawn','socket.connect','socket.getaddrinfo'}:
        BLOCKED.append(event);raise RuntimeError('Pure registry check blocks process/network actions')
sys.addaudithook(no_process_or_network)
from linked_ablation_execution import freeze,registry


class RegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Windows platform.platform() may invoke cmd /c ver; metadata is a fake
        # fixture here, while the real freeze retains its normal environment probe.
        with patch.object(freeze.platform,'platform',return_value='pure-fixture-platform'):
            cls.d=freeze.make_declaration([])

    def test_exact_human_scope_and_six_recipes(self):
        d=registry.validate_declaration(deepcopy(self.d))
        self.assertEqual([(s['case_id'],s['variant']) for s in d['slots']],registry.ORDER)
        self.assertEqual(d['budgets'],registry.BUDGETS)
        self.assertFalse(d['K168_authorized_here']);self.assertFalse(d['deadline_remainder_authorized_here'])

    def test_authority_budget_and_order_fail_closed(self):
        for field,value in [('authorized',False),('scientific_execution_enabled',False),('authorization_origin','old budget')]:
            d=deepcopy(self.d);d[field]=value
            with self.assertRaises(ValueError):registry.validate_declaration(d,check_sources=False)
        d=deepcopy(self.d);d['budgets']['method_s']=301
        with self.assertRaises(ValueError):registry.validate_declaration(d,check_sources=False)
        d=deepcopy(self.d);d['slots'].reverse()
        with self.assertRaises(ValueError):registry.validate_declaration(d,check_sources=False)

    def test_A_budget_and_BC_toggle_drift(self):
        for variant,key,value in [('A','scene_slice_s',60),('B','preeliminate_closed_anchors',True),
                                  ('C','preeliminate_closed_anchors',False)]:
            d=deepcopy(self.d);d['cases'][0]['recipes'][variant]['kwargs'][key]=value
            with self.assertRaises(ValueError):registry.validate_declaration(d,check_sources=False)

    def test_joint_model_or_solver_change_still_rejected(self):
        d=deepcopy(self.d);d['cases'][0]['common']['builder_options']['relax_auxiliary_integrality']=False
        for r in d['cases'][0]['recipes'].values():r['kwargs']['builder_options']['relax_auxiliary_integrality']=False
        with self.assertRaises(ValueError):registry.validate_declaration(d)
        d=deepcopy(self.d);d['solver_options']['IntegerTolerance']='1e-5'
        with self.assertRaises(ValueError):registry.validate_declaration(d)

    def test_old_or_foreign_output_and_claim_not_created(self):
        d=deepcopy(self.d);d['output_directory']='research/chapter3_experiments/results/p0_execution01'
        with self.assertRaises(ValueError):registry.validate_declaration(d,check_sources=False)
        with self.assertRaises(ValueError):registry.load_declaration(HERE/'fake.json')
        self.assertFalse(registry.GLOBAL_CLAIM.exists())
        self.assertFalse((registry.OUT/'declaration.json').exists())


def main(out):
    if out.exists():raise FileExistsError('Checks are append-only')
    result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(RegistryTests))
    report={'protocol':'K173-pure-registry-gate-v1','passed':result.wasSuccessful() and not BLOCKED,
        'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
        'guard':{'blocked':BLOCKED,'research_calls':0,'native_calls':0,'thermal_calls':0,
                 'declaration_created':False,'claim_created':False},
        'source_sha256':{p.relative_to(registry.REPO).as_posix():registry.sha(p)
            for p in (HERE/'registry.py',HERE/'freeze.py',Path(__file__))}}
    out.mkdir(parents=True)
    registry.write_new(out/'checks.json',report)
    print(json.dumps({'passed':report['passed'],'tests':result.testsRun,'blocked':BLOCKED}))
    if not report['passed']:raise SystemExit(1)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    main(p.parse_args().out)
