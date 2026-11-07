"""K176 exact freeze/recipe checks, no real declaration or research execution."""
import argparse
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from linked_release_execution import registry as r,freeze
BLOCKED=[]
def guard(event,args):
    if event=='import' and args[0].split('.')[0] in {'numpy','scipy','matlab','thermal','milp','inputs','matlab_bridge','linked_method','linked_release_method'}:
        BLOCKED.append(event);raise RuntimeError('No science')
    if event in {'subprocess.Popen','os.system','socket.connect','socket.getaddrinfo'}:
        BLOCKED.append(event);raise RuntimeError('No process/network')

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.object(freeze.platform,'platform',return_value='fixture-only'):
            cls.d=freeze.make_declaration([])
    def test_exact_two_and_caps(self):
        d=r.validate_declaration(deepcopy(self.d));self.assertEqual(len(d['slots']),2)
        self.assertEqual(d['budgets'],r.BUDGETS);self.assertFalse(d['K168_authorized_here'])
        self.assertFalse(d['deadline_remainder_authorized_here'])
    def test_old_order_or_extra_call_forbidden(self):
        for slots in (list(reversed(self.d['slots'])),self.d['slots']+[self.d['slots'][0]]):
            d=deepcopy(self.d);d['slots']=slots
            with self.assertRaises(ValueError):r.validate_declaration(d,check_sources=False)
    def test_budget_authority_output_immutable(self):
        for field,value in [('authorized',False),('authorization_origin','old budget'),('output_directory','old output')]:
            d=deepcopy(self.d);d[field]=value
            with self.assertRaises(ValueError):r.validate_declaration(d,check_sources=False)
        d=deepcopy(self.d);d['budgets']['method_s']=301
        with self.assertRaises(ValueError):r.validate_declaration(d,check_sources=False)
    def test_recipe_or_model_or_solver_drift(self):
        for mutate in (lambda d:d['cases'][0]['recipes']['conditional_release']['kwargs'].update(scene_slice_s=61),
            lambda d:d['cases'][0]['common'].update(start_grid_ms='1'),
            lambda d:d['solver_options'].update(IntegerTolerance='1e-5'),
            lambda d:d['cases'][0]['recipes']['conditional_release']['kwargs'].update(preeliminate_closed_anchors=True)):
            d=deepcopy(self.d);mutate(d)
            with self.assertRaises(ValueError):r.validate_declaration(d)
    def test_wrong_source_or_input_rejected(self):
        d=deepcopy(self.d);d['source_sha256']['research/chapter3_experiments/linked_method.py']='wrong'
        with self.assertRaises(ValueError):r.validate_declaration(d)
        with self.assertRaises(ValueError):r.load_declaration(HERE/'fake.json')
    def test_no_real_claim_or_declaration(self):
        self.assertFalse(r.GLOBAL_CLAIM.exists());self.assertFalse((r.OUT/'declaration.json').exists())

def main(out):
    if out.exists():raise FileExistsError('append-only')
    raw=io.StringIO();result=unittest.TextTestRunner(stream=raw,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    report={'passed':result.wasSuccessful() and not BLOCKED,'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'guard':{'blocked':BLOCKED},'research_calls':0,'thermal_calls':0,'native_calls':0,'real_declaration_or_claim_created':False,'source_sha256':{p.relative_to(r.REPO).as_posix():r.sha(p) for p in (Path(__file__),HERE/'registry.py',HERE/'freeze.py')}}
    out.mkdir(parents=True);r.write_new(out/'checks.json',report);(out/'unittest.txt').write_text(raw.getvalue(),'utf-8')
    print(json.dumps({'passed':report['passed'],'tests':result.testsRun,'blocked':BLOCKED}))
    if not report['passed']:raise SystemExit(1)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);sys.addaudithook(guard);main(p.parse_args().out)
