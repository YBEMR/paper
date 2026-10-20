"""One external process clock; the method driver owns research budgets."""
from pathlib import Path
from datetime import datetime, timezone
import json
import os
import subprocess
import sys
import time

OUT = Path(__file__).resolve().parent
REPO = next(p for p in OUT.parents if (p/'AGENTS.md').is_file())

def main():
    with (OUT/'launcher_claim.json').open('x', encoding='utf-8') as stream:
        json.dump({'started_at_utc':datetime.now(timezone.utc).isoformat(),
                   'one_process_only':True, 'no_retry':True}, stream)
    started = time.monotonic()
    code = None
    error = None
    environment = dict(os.environ)
    environment['PYTHONUTF8'] = '1'
    try:
        with (OUT/'console.txt').open('x', encoding='utf-8') as log:
            process = subprocess.Popen([sys.executable, '-B',
                str(REPO/'research/chapter3_experiments/run_linked_pair.py'),
                '--run', '--out', str(OUT)], cwd=REPO, env=environment,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace',
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            for line in process.stdout:
                log.write(line)
                log.flush()
                print(line, end='', flush=True)
            code = process.wait()
    except Exception as exc:
        error = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        timing = {'complete_driver_process_wall_s':time.monotonic()-started,
                  'returncode':code, 'error':error,
                  'clock_scope':'before driver launch through complete exit, including imports, all method tails and cleanup; own receipt write excluded',
                  'research_call_limit':2, 'per_method_evidence_budget_s':300,
                  'new_evidence_created_by_launcher':False}
        (OUT/'launcher_timing.json').write_text(json.dumps(timing,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return code

if __name__=='__main__':
    raise SystemExit(main())
