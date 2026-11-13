"""Real controller/Job/Git identity controls. Never permit a scientific worker."""
import ast,copy,io,json,os,shutil,subprocess,sys,time,types,unittest
from pathlib import Path
from unittest.mock import patch
from core import read,save,sha,Clock
from environment import snapshot
from identity import verify_commit,GitIdentityError
from batch import launch_arm,read_terminal,accumulate,batch_exit_code
import test_control,test_abc

OUT=None
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
GIT=Path('F:/Git/Git/mingw64/bin/git.exe')
LEGACY_GIT=Path('F:/Git/Git/cmd/git.exe')
class EntryTests(unittest.TestCase):
    def setUp(self):self.out=OUT/self._testMethodName;self.out.mkdir()
    def fixture(self,git_path=GIT,bad_hash=False,corrupt_blob=False):
        root=self.out/'fixture';repo=root/'work/publish_repo';package=repo/'research/control_executor';package.mkdir(parents=True)
        (repo/'.gitattributes').write_text('* -text\n',encoding='utf-8',newline='\n')
        code={p.name:sha(p) for p in HERE.glob('*.py')}
        for p in HERE.glob('*.py'):shutil.copy2(p,package/p.name)
        if corrupt_blob:(package/'native.py').write_bytes(b'# CONTROL CORRUPTED COMMITTED COPY\n'+(package/'native.py').read_bytes())
        small=root/'work/control_input.json';save(small,dict(artificial=True,not_R1=True))
        baseline=read(ROOT/'work/cplex_ABC_v2/plan.json')
        plan=dict(protocol='D285-CPLEX-fresh-ABC-entry-fixed-v1',ready_to_request_independent_scientific_authorization=True,
            code_hashes=code,repository_package='research/control_executor',execution_directory='work/science_FORBIDDEN',
            input_hashes={'work/control_input.json':sha(small)},evaluation_source_hashes={},runtime_hashes={},
            environment=snapshot(),control_git=dict(path=str(git_path),sha256='0'*64 if bad_hash else sha(git_path)),
            native_runtime=dict(python=sys.executable),limits=baseline['limits'])
        path=package/'plan.json';save(path,plan)
        def git(*args):
            return subprocess.check_output([str(GIT),'-c','core.longpaths=true','-c','commit.gpgsign=false','-c','user.name=CONTROL',
                '-c','user.email=control@example.invalid','-C',str(repo),*args],stderr=subprocess.PIPE)
        git('init','-q');git('add','.');git('commit','-qm','Pure control fixture; no scientific execution')
        commit=git('rev-parse','HEAD').decode().strip();h=sha(path)
        approval=dict(protocol='D285-CONTROL-ENTRY-ONLY-v1',decision='CONTROL_ONLY',plan_sha256=h,
            maximum_scientific_workers=0,maximum_solve_calls=0,frozen_commit=commit)
        approved=root/'control_approval.json';save(approved,approval)
        save(self.out/'fixture_identity.json',dict(fixture_commit=commit,plan_sha256=h,
            current_executor_hashes=code,scientific_calls=0,artificial_repository=True))
        return root,path,plan,h,approval,approved
    def launch(self,fixture,approval_override=None,entry_only=True):
        root,path,plan,h,approval,approved=fixture
        if approval_override:
            approval.update(approval_override);approved=root/'changed_approval.json';save(approved,approval)
        folder=root/'control_arm';folder.mkdir()
        r=launch_arm('A',root,HERE,path,h,plan,folder,approved,entry_only=entry_only)
        save(self.out/'observed_launch.json',r)
        self.assertTrue(r['outer_cleanup_ok']);self.assertEqual(r['outer_job_accounting']['active_processes'],0)
        self.assertEqual(r['outer_job_limits']['active_limit'],2)
        self.assertEqual(r['outer_job_limits']['job_memory'],3758096384)
        self.assertFalse((root/'work/science_FORBIDDEN').exists())
        self.assertFalse((folder/'A/owned_process.json').exists());self.assertFalse((folder/'A/claim.json').exists())
        self.assertFalse((folder/'A/runtime.json').exists());self.assertFalse((folder/'A/native_response.json').exists())
        return r,folder/'A'
    def test_real_controller_all_sources_verified_under_actual_Job(self):
        f=self.fixture();r,out=self.launch(f)
        self.assertEqual(r['exit_code'],0);self.assertEqual(r['receipt']['outcome']['outcome'],'CONTROL_ENTRY_ONLY_VERIFIED')
        s=read(out/'entry_git_summary.json');self.assertTrue(s['passed'])
        self.assertEqual(len(s['checks']),1+len(f[2]['code_hashes']))
        self.assertTrue(all(x['matches'] and x['command'][0]==str(GIT) for x in s['checks']))
        self.assertFalse(r['receipt']['scientific_worker_started'])
    def test_parent_claim_failure_retains_structured_early_receipt(self):
        f=self.fixture()
        def wrong_claim(path,value):
            value=copy.deepcopy(value)
            if Path(path).name=='A_launch.json':value['parent_pid']+=1
            save(path,value)
        with patch('batch.save',side_effect=wrong_claim):r,out=self.launch(f)
        self.assertEqual(r['exit_code'],1)
        self.assertEqual(r['receipt']['outcome']['outcome'],'CONTROL_ENTRY_UNCLAIMED_FAILURE')
        self.assertIn('Batch claim mismatch',r['receipt']['entry_error']['error']['message'])
        self.assertFalse(out.exists())
    def test_original_PATH_launcher_failure_has_raw_receipt(self):
        r,out=self.launch(self.fixture(LEGACY_GIT))
        self.assertEqual(r['exit_code'],1);self.assertEqual(r['receipt']['outcome']['outcome'],'CONTROL_ENTRY_FAILURE')
        first=read(out/'entry_git_001.json');self.assertEqual(first['returncode'],1)
        self.assertIn(b'error launching git',(out/first['stderr_file']).read_bytes())
        self.assertEqual(accumulate(set(),'A',r),set('ABC'))
    def test_invalid_commit_original_git_error_preserved(self):
        r,out=self.launch(self.fixture(),dict(frozen_commit='f'*40))
        first=read(out/'entry_git_001.json');self.assertNotEqual(first['returncode'],0)
        self.assertTrue((out/first['stderr_file']).read_bytes());self.assertEqual(first['stdout_bytes'],0)
        self.assertEqual(len(read(out/'entry_git_summary.json')['checks']),1)
        self.assertEqual(r['receipt']['outcome']['stop_scope'],'GLOBAL')
    def test_committed_source_mismatch_preserves_bytes(self):
        r,out=self.launch(self.fixture(corrupt_blob=True))
        s=read(out/'entry_git_summary.json');self.assertFalse(s['passed'])
        last=s['checks'][-1];self.assertEqual(last['name'],'native.py');self.assertEqual(last['returncode'],0)
        self.assertNotEqual(last['stdout_sha256'],last['expected_blob_sha256'])
        self.assertTrue((out/last['stdout_file']).read_bytes().startswith(b'# CONTROL CORRUPTED'))
    def test_Git_binary_hash_drift_no_PATH_fallback(self):
        r,out=self.launch(self.fixture(bad_hash=True))
        s=read(out/'entry_git_summary.json');self.assertEqual(s['checks'],[]);self.assertFalse(s['passed'])
        self.assertIn('identity drift',s['error']['message'])
    def test_control_approval_cannot_start_scientific_worker(self):
        r,out=self.launch(self.fixture(),entry_only=False)
        self.assertEqual(r['exit_code'],1);self.assertFalse((out/'entry_git_summary.json').exists())
        self.assertIn('approval',read(out/'entry_failure.json')['error']['message'])
    def test_old_D284_approval_cannot_start_scientific_worker(self):
        r,out=self.launch(self.fixture(),dict(protocol='D284-CPLEX-fresh-ABC-approval-v1',decision='APPROVE'),entry_only=False)
        self.assertEqual(r['exit_code'],1);self.assertFalse((out/'claim.json').exists())
    def test_scientific_approval_cannot_remove_entry_only_stop(self):
        r,out=self.launch(self.fixture(),dict(protocol='D285-CPLEX-fresh-ABC-approval-v1',decision='APPROVE'))
        self.assertEqual(r['exit_code'],1);self.assertFalse((out/'claim.json').exists())
    def test_timeout_stdout_stderr_preserved_without_retry(self):
        root,path,plan,h,a,_=self.fixture();e=self.out/'timeout';e.mkdir();calls=[]
        def fail(command,**kw):
            calls.append((command,kw))
            raise subprocess.TimeoutExpired(command,kw['timeout'],output=b'partial stdout',stderr=b'partial stderr')
        with self.assertRaises(GitIdentityError):verify_commit(root,HERE,plan,a,e,Clock(time.monotonic()),path,runner=fail)
        self.assertEqual(len(calls),1);self.assertLessEqual(calls[0][1]['timeout'],5)
        first=read(e/'entry_git_001.json')
        self.assertEqual(first['error']['type'],'TimeoutExpired')
        self.assertEqual((e/first['stdout_file']).read_bytes(),b'partial stdout')
        self.assertEqual((e/first['stderr_file']).read_bytes(),b'partial stderr')
    def test_startup_error_preserves_original_exception(self):
        root,path,plan,h,a,_=self.fixture();e=self.out/'oserror';e.mkdir()
        def fail(*x,**kw):raise OSError(8,'CONTROL original process launch error')
        with self.assertRaises(GitIdentityError):verify_commit(root,HERE,plan,a,e,Clock(time.monotonic()),path,runner=fail)
        self.assertIn('original process launch error',read(e/'entry_git_001.json')['error']['message'])
    def test_expired_identity_entry_does_not_read_git(self):
        root,path,plan,h,a,_=self.fixture();e=self.out/'late';e.mkdir();calls=[]
        with self.assertRaises(TimeoutError):verify_commit(root,HERE,plan,a,e,Clock(time.monotonic()-551),path,runner=lambda *x,**k:calls.append(1))
        self.assertEqual(calls,[]);self.assertFalse(read(e/'entry_git_summary.json')['passed'])
    def run_batch(self,fixture):
        root,path,plan,h,a,approved=fixture;out=root/'control_batch'
        argv=[sys.executable,'-B',str(HERE/'batch.py'),'--workspace',str(root),'--plan',str(path),'--expected-sha',h,
            '--approval',str(approved),'--entry-only','--control-output',str(out)]
        started=time.monotonic();p=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45,creationflags=subprocess.CREATE_NO_WINDOW)
        (self.out/'batch.stdout.bin').write_bytes(p.stdout);(self.out/'batch.stderr.bin').write_bytes(p.stderr)
        save(self.out/'batch_host.json',dict(exit_code=p.returncode,wall_s=time.monotonic()-started,scientific_calls=0))
        self.assertFalse((root/'work/science_FORBIDDEN').exists())
        return p,out,read(out/'batch_receipt.json')
    def test_actual_batch_three_real_entries_stop_before_science(self):
        p,out,r=self.run_batch(self.fixture());self.assertEqual(p.returncode,0)
        self.assertEqual(r['blocked_arms'],[]);self.assertEqual(r['scientific_calls'],0)
        for arm in 'ABC':
            row=r['arms'][arm];self.assertTrue(row['outer_cleanup_ok'])
            self.assertEqual(row['receipt']['outcome']['outcome'],'CONTROL_ENTRY_ONLY_VERIFIED')
            self.assertFalse((out/arm/'claim.json').exists())
            self.assertTrue(read(out/arm/'entry_git_summary.json')['passed'])
        self.assertFalse(read(out/'batch_claim.json')['approval_consumed'])
    def test_actual_failed_A_global_stop_and_batch_nonzero(self):
        p,out,r=self.run_batch(self.fixture(LEGACY_GIT));self.assertEqual(p.returncode,1)
        self.assertEqual(r['blocked_arms'],list('ABC'))
        self.assertEqual(r['arms']['A']['receipt']['outcome']['outcome'],'CONTROL_ENTRY_FAILURE')
        self.assertTrue(all(r['arms'][a]['skipped'] for a in 'BC'))
        self.assertTrue((out/'A/entry_git_001.stderr.bin').exists())
    def test_batch_own_identity_error_structured_no_arm_launch(self):
        p,out,r=self.run_batch(self.fixture(bad_hash=True));self.assertEqual(p.returncode,1)
        self.assertTrue((out/'batch_entry_failure.json').exists())
        self.assertTrue(all(r['arms'][a]['skipped'] for a in 'ABC'))
        self.assertFalse(any((out/a).exists() for a in 'ABC'))
    def test_batch_exit_distinguishes_global_failure_from_ordinary_timeout(self):
        self.assertEqual(batch_exit_code(dict(blocked_arms=[])),0)
        self.assertEqual(batch_exit_code(dict(blocked_arms=list('ABC'))),1)
    def test_science_and_native_source_unchanged(self):
        old=ROOT/'work/cplex_ABC_v2'
        for name in ('science.py','representation.py','reduction_replay.py','worker.py','native.py','native_adapter.py','transport_contract.py','windows_job.py'):
            self.assertEqual((HERE/name).read_bytes(),(old/name).read_bytes(),name)
    def test_no_PATH_git_calls_in_fixed_sources(self):
        for name in ('batch.py','controller.py','identity.py'):
            source=(HERE/name).read_text()
            self.assertNotIn("['git'",source);self.assertNotIn('shell=True',source)

def main():
    global OUT
    OUT=Path(sys.argv[1]).resolve();OUT.mkdir(exist_ok=False);test_control.OUT=OUT;test_abc.OUT=OUT
    suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(test_control.Tests),
        unittest.defaultTestLoader.loadTestsFromTestCase(test_abc.Tests),unittest.defaultTestLoader.loadTestsFromTestCase(EntryTests)])
    buf=io.StringIO();t=time.monotonic();r=unittest.TextTestRunner(stream=buf,verbosity=2).run(suite)
    (OUT/'unittest.txt').write_text(buf.getvalue(),encoding='utf-8',newline='\n')
    result=dict(passed=r.wasSuccessful(),tests_run=r.testsRun,failures=len(r.failures),errors=len(r.errors),elapsed_s=time.monotonic()-t,
        CPLEX_imported='cplex' in sys.modules,CPLEX_objects=0,optimization_calls=0,full_R1_builds=0,thermal_evaluations=0,
        original_science_imported=any(x in sys.modules for x in ('milp','thermal','complement_gate')),
        code_hashes={p.name:sha(p) for p in sorted(HERE.glob('*.py'))},scope='Pure controls; real Git fixture repos and real controller/Job entry; scientific worker explicitly forbidden')
    save(OUT/'results.json',result);print(buf.getvalue());return 0 if r.wasSuccessful() else 1
if __name__=='__main__':raise SystemExit(main())

