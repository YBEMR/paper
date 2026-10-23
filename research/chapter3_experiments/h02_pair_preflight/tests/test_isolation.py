"""Pure R packet subprocess mock with no physical or search implementation."""
import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from h02_pair_preflight.paired_response_input_view import paired_response_input_view,planner_packet,HERE,CORE
from h02_pair_preflight.common import encoded

WORKER_REPORTS=[]
class Isolation(unittest.TestCase):
    def test_R_process_reads_only_own_public_payload_and_cache(self):
        p=planner_packet(paired_response_input_view('base__R1'),'R')
        with tempfile.TemporaryDirectory(prefix='h02_isolation_mock_') as d:
            root=Path(d); r=root/'R'; r.mkdir(); h=root/'sealed_H'; h.mkdir()
            # Sentinel is NOT H data; child must deny access before reading it.
            sealed=h/'truth_H.json'; sealed.write_text('DENY_SENTINEL_NOT_PHYSICAL_INPUT',encoding='utf-8')
            env={k:os.environ[k] for k in ('SystemRoot','WINDIR','TEMP','TMP') if k in os.environ}
            proc=subprocess.run([sys.executable,'-B',str(HERE/'isolation_mock_worker.py'),'--root',str(r),'--forbidden-path',str(sealed),'--forbidden-path',str(CORE/'config_v01.json')],input=encoded(p),capture_output=True,cwd=r,env=env,timeout=30)
            self.assertEqual(proc.returncode,0,proc.stderr.decode('utf-8',errors='replace')+' '+proc.stdout.decode('utf-8',errors='replace'))
            report=json.loads(proc.stdout); WORKER_REPORTS.append(report)
            self.assertTrue(report['passed']); self.assertFalse(report['formal_budget_authorized'])
