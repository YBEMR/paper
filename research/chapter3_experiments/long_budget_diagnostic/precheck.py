"""Pure wrapper checks and exact source/input binding; never invoke research."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import run_once as r

class WrapperTests(unittest.TestCase):
    def test_resource_gate(self):
        c=dict(token_is_appcontainer=False,matlab_processes=[],physical_available_bytes=3*1024**3,
            commit_available_bytes=6*1024**3,disk_free_bytes=3*1024**3)
        self.assertTrue(r.resource_ok(c))
        for key,value in [('token_is_appcontainer',True),('matlab_processes',[{'pid':1}]),
            ('physical_available_bytes',0),('commit_available_bytes',0),('disk_free_bytes',0)]:
            self.assertFalse(r.resource_ok(dict(c,**{key:value})))

    def test_exclusive_claim(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'claim.json';r.write_new(p,{'n':1})
            with self.assertRaises(FileExistsError):r.write_new(p,{'n':2})
            self.assertEqual(r.read(p),{'n':1})

    def test_exact_dispatch_one_method_root(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t);call=out/'method';seen=[]
            raw,config,instance={'raw':1},{'config':2},{'instance':3}
            hashes=dict(zip(('raw_config_sha256','config_sha256','input_sha256'),map(r.canonical,(raw,config,instance))))
            d={'input_declaration':{'input_identities':hashes}}
            r.write_new(out/'declaration.json',d)
            budget=SimpleNamespace(start=1000.,deadline=4600.,remaining=3600.,check=lambda:None,phase=lambda _:contextlib.nullcontext())
            def fresh(problem,b):
                self.assertEqual(problem,'base__R1');self.assertIs(b,budget);seen.append('fresh');return raw,config,instance
            def bound(inst,unused,b):
                self.assertIs(b,budget);seen.append('L0');return {'bound':'fixture'}
            def builder(*a,**kw):raise AssertionError('Model construction forbidden in mock')
            def session(*a,**kw):raise AssertionError('Native call forbidden in mock')
            def whole(loader,folder,**kw):
                self.assertEqual(kw['seconds'],3600);self.assertEqual(kw['feedback_kind'],'conditional')
                self.assertEqual(kw['model_builder'].keywords,dict(prefilter_deadlines=True,cumulative_precedence=False))
                self.assertEqual(kw['session_factory'].keywords,dict(cut_max_iterations=10))
                folder.mkdir();self.assertEqual(loader(budget),(config,instance));seen.append('whole')
                return {'state':'UNRESOLVED','safe_upper_bound_J':None}
            fake=(SimpleNamespace(fresh_input=fresh),SimpleNamespace(execute_formal_milp=whole),
                SimpleNamespace(build_model=builder),SimpleNamespace(MatlabSession=session),SimpleNamespace(independent_lower_bound=bound))
            audit=SimpleNamespace(audit_result=lambda *a,**k:{'usable_U_J':None})
            with (patch.object(r,'OUT',out),patch.object(r,'CALL',call),patch.object(r,'admission',return_value=d),
                 patch.object(r,'context',return_value={'token_is_appcontainer':False}),patch.object(r,'bind',return_value=fake),
                 patch.object(r,'modules_used',return_value={}),patch.dict(sys.modules,{'read_audit':audit})):
                self.assertEqual(r.method(),0)
            self.assertEqual(seen,['fresh','L0','whole'])
            self.assertEqual(r.read(call/'method_budget_identity.json')['deadline'],4600)
            self.assertFalse(r.read(out/'method_return.json')['post_authorized'])

def run():
    start=time.monotonic();d=r.admission()
    temporary=r.REPO/'.runtime/k187_pure'
    temporary.mkdir(parents=True,exist_ok=True);tempfile.tempdir=str(temporary)
    # Importing frozen code does not execute any optimizer or thermal evaluator.
    p,_,_,_,_=r.bind()
    import thermal,matlab_bridge,method_runner
    def forbidden(*a,**k):raise AssertionError('Research operation forbidden during pure precheck')
    with patch.object(thermal,'evaluate_candidate',forbidden),patch.object(matlab_bridge,'MatlabSession',forbidden),patch.object(method_runner,'execute_milp',forbidden):
        raw,config,instance=p.fresh_input('base__R1')
        actual=dict(zip(('raw_config_sha256','config_sha256','input_sha256'),map(r.canonical,(raw,config,instance))))
        if actual!=d['input_declaration']['input_identities']:raise AssertionError('Original input mismatch')
    import test_read_audit
    suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(WrapperTests),
        unittest.defaultTestLoader.loadTestsFromModule(test_read_audit)])
    buffer=io.StringIO();res=unittest.TextTestRunner(stream=buffer,verbosity=2).run(suite)
    (r.OUT/'pure_tests.txt').write_text(buffer.getvalue(),encoding='utf-8')
    import platform,numpy,scipy,mpmath
    old=r.read(r.OLD/'calls/base__R1/whole_milp/result.json')['environment']
    checks=dict(tests_passed=res.wasSuccessful(),source_count=len(d['source_sha256']),input_identity_exact=True,
        python_version_same=old['python']==sys.version,platform_same=old['platform']==platform.platform())
    record=dict(passed=all(v for k,v in checks.items() if k!='source_count'),checks=checks,test_count=res.testsRun,
        new_research_calls=0,native_starts=0,thermal_integrations=0,model_constructions=0,
        declaration_sha256=r.sha(r.OUT/'declaration.json'),actual_modules=r.modules_used(d),
        environment={'python':sys.version,'platform':platform.platform(),'numpy':numpy.__version__,'scipy':scipy.__version__,'mpmath':mpmath.__version__},
        elapsed_s=time.monotonic()-start)
    r.write_new(r.OUT/'pure_checks.json',record)
    print(json.dumps({k:v for k,v in record.items() if k not in ('actual_modules','environment')}))
    return 0 if record['passed'] else 2

if __name__=='__main__':raise SystemExit(run())
