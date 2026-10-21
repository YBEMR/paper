"""One 600-second supervised continuation; the original call is never rerun."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

PREP = Path(__file__).resolve().parent
HERE = PREP.parents[1]
REPO = HERE.parents[1]
OUT = HERE/'results/linked_five_open_pair01'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    first = json.loads((OUT/'launcher_result.json').read_text(encoding='utf-8'))
    if first['outer_watchdog_stopped'] or first['process_wall_s']+600 > 900:
        raise RuntimeError('Original cumulative active-process watchdog cannot be met')
    binding = {p.name: sha(p) for p in (Path(__file__), PREP/'recover_remaining.py',
        PREP/'recovery_precheck01.json', PREP/'recovery_protocol.md', OUT/'analysis01/analyze.py')}
    with (OUT/'recovery_launcher_claim.json').open('x', encoding='utf-8') as f:
        json.dump({'created_at_utc': datetime.now(timezone.utc).isoformat(),
            'hard_wall_s': 600, 'bindings': binding, 'no_retry': True,
            'original_process_wall_s': first['process_wall_s'],
            'pause_scope': 'read-only diagnosis/precheck between separately supervised processes; not method time'}, f, indent=2)
    command = [sys.executable, '-B', str(PREP/'recover_remaining.py'), '--run', '--execution-authorized']
    start = time.monotonic()
    stopped = False
    with (OUT/'recovery_launcher.log').open('wb') as stream:
        p = subprocess.Popen(command, cwd=REPO, stdout=stream, stderr=subprocess.STDOUT,
                             creationflags=subprocess.CREATE_NO_WINDOW)
        print(json.dumps({'event': 'REMAINING_CALL_STARTED', 'pid': p.pid,
            'utc': datetime.now(timezone.utc).isoformat(), 'hard_wall_s': 600}), flush=True)
        while p.poll() is None:
            remaining = 600-(time.monotonic()-start)
            if remaining <= 0:
                print('K148 continuation watchdog expired; stopping only its owned process tree.', flush=True)
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
    result['cumulative_active_process_wall_s'] = first['process_wall_s']+result['process_wall_s']
    with (OUT/'recovery_launcher_result.json').open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result), flush=True)
    return 0 if result['returncode'] == 0 and not stopped else 1


if __name__ == '__main__':
    raise SystemExit(main())
