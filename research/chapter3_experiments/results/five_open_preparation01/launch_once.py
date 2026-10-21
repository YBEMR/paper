"""Run exactly the frozen K148 command, with a 900-second outer watchdog."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parents[2]
REPO = HERE.parents[1]
OUT = HERE/'results/linked_five_open_pair01'


def main():
    # This guard is independent of the method-level/global single-use claims.
    claim = OUT/'launcher_claim.json'
    with claim.open('x', encoding='utf-8') as f:
        json.dump({'created_at_utc': datetime.now(timezone.utc).isoformat(),
            'hard_wall_s': 900, 'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'no_retry': True}, f, indent=2)
    command = [sys.executable, '-B', str(HERE/'run_five_open_pair.py'), '--run',
        '--execution-authorized', '--out', str(OUT)]
    start = time.monotonic()
    stopped = False
    with (OUT/'launcher.log').open('wb') as stream:
        p = subprocess.Popen(command, cwd=REPO, stdout=stream, stderr=subprocess.STDOUT,
                             creationflags=subprocess.CREATE_NO_WINDOW)
        print(json.dumps({'event': 'PAIR_STARTED', 'pid': p.pid,
            'utc': datetime.now(timezone.utc).isoformat(), 'hard_wall_s': 900}), flush=True)
        while p.poll() is None:
            remaining = 900-(time.monotonic()-start)
            if remaining <= 0:
                print('K148 outer watchdog expired; stopping only its owned process tree.', flush=True)
                subprocess.run(['taskkill', '/PID', str(p.pid), '/T', '/F'],
                    capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                stopped = True
                break
            try:
                p.wait(timeout=min(30, remaining))
            except subprocess.TimeoutExpired:
                pass
    result = {'returncode': p.poll(), 'outer_watchdog_stopped': stopped,
        'process_wall_s': time.monotonic()-start, 'command': command,
        'completed_at_utc': datetime.now(timezone.utc).isoformat(), 'no_retry': True}
    with (OUT/'launcher_result.json').open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result), flush=True)
    return 0 if result['returncode'] == 0 and not stopped else 1


if __name__ == '__main__':
    raise SystemExit(main())
