import argparse,json,os,sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1] if False else 'C:\\Users\\86130\\Documents\\Codex\\2026-11-12\\https-github-com-ybemr-paper-https-2\\work\\cplex_ABC_v2')
from core import read,save,sha
p=argparse.ArgumentParser();p.add_argument('--arm');p.add_argument('--batch');p.add_argument('--t0',type=float)
a,_=p.parse_known_args();b=Path(a.batch);claim=read(b/(a.arm+'_launch.json'))
assert sys.stdin.readline().strip()=='D284_ARM_GO '+claim['nonce']
o=b/a.arm;o.mkdir();save(o/'controller_receipt.json',dict(plan_sha256='h',synthetic=True,pid=os.getpid(),outcome=dict(outcome='TIME_LIMIT',stop_scope='THIS_RUN',reasons=[],strict_success=False,scientific_snapshot_accepted=True)))
save(o/'controller_completion.json',dict(within_method_window=True,after_receipt_and_hash_elapsed_s=time.monotonic()-a.t0,receipt_sha256=sha(o/'controller_receipt.json')))
