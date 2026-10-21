"""Record the local runtime and test the MATLAB toolbox license, without solving.

Each run has a new output directory. A successful license checkout is not a
solver correctness, numerical guarantee, or formal experiment precheck.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DEFAULT_MATLAB = Path('F:/Matlab2023/Program_Files/MATLAB_R2023b/bin/matlab.exe')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE / 'results/environment01')
    parser.add_argument('--matlab', type=Path, default=DEFAULT_MATLAB)
    parser.add_argument('--timeout', type=float, default=60)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    info = {
        'scope': 'environment_only_no_solver_or_research_case',
        'python': sys.version,
        'python_executable': sys.executable,
        'os': platform.platform(),
        'matlab_executable': str(args.matlab),
        'packages': {},
        'formal_experiments_ready': False,
        'source_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in [Path(__file__), HERE / 'environment_probe.m']},
    }
    for name in ['numpy', 'scipy', 'mpmath']:
        try:
            info['packages'][name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            info['packages'][name] = None
    # Same workspace-local preferences as the existing MATLAB wrapper.
    prefs = REPO / '.runtime/matlab_prefs'
    prefs.mkdir(parents=True, exist_ok=True)
    info['matlab_prefdir'] = str(prefs)
    quote = lambda p: p.as_posix().replace("'", "''")
    script = "addpath('%s'); environment_probe('%s');" % (
        quote(HERE), quote(folder / 'matlab.json'))
    start = time.monotonic()
    try:
        with (folder / 'matlab.log').open('w', encoding='utf-8') as log:
            proc = subprocess.Popen(
                [str(args.matlab), '-batch', script],
                env=dict(os.environ, MATLAB_PREFDIR=str(prefs)),
                stdout=log, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            info['pid'] = proc.pid
            (folder / 'started.json').write_text(json.dumps({
                'pid': proc.pid, 'timeout_seconds': args.timeout,
                'matlab_prefdir': str(prefs)}, indent=2) + '\n', encoding='utf-8')
            try:
                info['returncode'] = proc.wait(timeout=args.timeout)
            except subprocess.TimeoutExpired:
                info['status'] = 'TIMEOUT'
                if os.name == 'nt':
                    cleanup = subprocess.run(
                        ['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                        stdout=log, stderr=subprocess.STDOUT, timeout=10)
                    info['cleanup_returncode'] = cleanup.returncode
                else:
                    proc.kill()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    info['cleanup_pending_pid'] = proc.pid
        if info.get('status') != 'TIMEOUT':
            if info.get('returncode') == 0 and (folder / 'matlab.json').exists():
                raw = json.loads((folder / 'matlab.json').read_text(encoding='utf-8-sig'))
                info['matlab'] = raw
                info['status'] = ('LICENSE_CHECKOUT_OK_NOT_SOLVER_VALIDATED'
                                  if raw['license_checkout'] and raw['intlinprog_path']
                                  else 'TOOLBOX_UNAVAILABLE')
            else:
                info['status'] = 'MATLAB_START_FAILED'
    except (OSError, subprocess.SubprocessError, ValueError, KeyError) as exc:
        info['status'] = 'ENVIRONMENT_ERROR'
        info['error'] = str(exc)
    info['wall_seconds'] = time.monotonic() - start
    (folder / 'environment.json').write_text(
        json.dumps(info, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': info['status'], 'output': str(folder)}, ensure_ascii=False))
    return 0 if info['status'] == 'LICENSE_CHECKOUT_OK_NOT_SOLVER_VALIDATED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
