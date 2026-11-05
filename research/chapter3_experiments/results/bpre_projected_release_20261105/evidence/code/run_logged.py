"""Log one explicit prepare/run invocation. Never retries or starts on import."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent


def save(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write('\n')


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in ('prepare', 'run'):
        raise ValueError('Usage: run_logged.py {prepare|run} <controller options>')
    stage = args[0]
    command = [sys.executable, '-B', str(HERE / 'live_variant.py'), *args]
    paths = {name: HERE / (stage + suffix) for name, suffix in (
        ('started', '_started.json'), ('record', '_command.json'), ('log', '.log'))}
    if any(path.exists() for path in paths.values()):
        raise FileExistsError('Refuse repeated stage or overwritten execution records')
    clock = time.perf_counter()
    record = dict(stage=stage, start_utc=datetime.now(timezone.utc).isoformat(),
        command_argv=command, cwd=str(HERE), status='STARTING', log=str(paths['log']),
        retries=0, native_or_scientific_launch_only_by_explicit_run=(stage == 'run'))
    save(paths['started'], record)
    process = None
    code = 2
    try:
        with paths['log'].open('xb') as log:
            process = subprocess.Popen(command, cwd=HERE, stdout=log, stderr=subprocess.STDOUT,
                env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'),
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            record['pid'] = process.pid
            print(json.dumps(dict(stage=stage, pid=process.pid, start_utc=record['start_utc'],
                                  status='PROCESS_STARTED')), flush=True)
            code = process.wait()
            record.update(status='COMPLETED' if code == 0 else 'FAILED', exit_code=code)
    except BaseException as error:
        observed = process.poll() if process is not None else None
        record.update(status='EXECUTION_OUTCOME_UNRESOLVED' if process is not None and observed is None
                      else 'LAUNCH_FAILED' if process is None else 'FAILED',
            exit_code=observed, error=type(error).__name__ + ': ' + str(error),
            traceback=traceback.format_exc(), no_retry=True,
            child_may_be_running=process is not None and observed is None)
    finally:
        record.update(end_utc=datetime.now(timezone.utc).isoformat(),
                      elapsed_seconds=time.perf_counter() - clock)
        save(paths['record'], record)
    print(json.dumps(record, ensure_ascii=False), flush=True)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
