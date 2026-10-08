"""Create-only precheck/certification records. No historical energy import."""
from pathlib import Path
import argparse
import json
import importlib.util
import sys
import time

import certificate as c


def save(path, data):
    with Path(path).open('x', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=c.a.v1.encode); f.write('\n')


def resolve_local(value):
    p = (c.HERE / value).resolve()
    if not p.is_relative_to(c.HERE.resolve()):
        raise ValueError('output_or_review_outside_package')
    return p


def main():
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=['precheck', 'certify'])
    p.add_argument('--output', required=True)
    p.add_argument('--ready')
    arg = p.parse_args()
    folder = resolve_local(arg.output)
    if arg.mode == 'precheck':
        folder.mkdir(parents=True, exist_ok=False)
        spec = importlib.util.spec_from_file_location('pulse_precheck', c.HERE / 'precheck.py')
        precheck = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(precheck)
        result = precheck.run()
        save(folder / 'result.json', result)
        print(json.dumps({'passed': result['passed'], 'checks': len(result['checks'])}))
        return 0 if result['passed'] else 1
    ready = json.loads(resolve_local(arg.ready).read_text(encoding='utf-8'))
    gate = resolve_local(ready['gate_path']); review = resolve_local(ready['review_path'])
    c.check_ready(ready, gate.read_bytes(), review.read_bytes())
    folder.mkdir(parents=True, exist_ok=False)
    # Input assembly and every proof check are charged to this same 20-second budget.
    budget = c.a.v2.Budget(seconds=20)
    bundle = c.expected_bundle()
    result = c.evaluate_safety_bundle(bundle, budget)
    if time.monotonic()-budget.start > 20 and result['status'] != 'candidate_violation':
        result.update(status='unresolved', budget_status='exhausted', reason='outer_wall_clock_limit')
        result.pop('safety_receipt', None)
    save(folder / 'result.json', result)
    save(folder / 'provenance.json', dict(hashes=c.identities(), readiness=ready,
                                       ready_path=arg.ready, ready_sha256=c.a.cp.sha(resolve_local(arg.ready)),
                                       stage='K33 sustained certificate only; zero new energy calls'))
    print(json.dumps({'status': result['status'], 'elapsed_s': result['elapsed_s']}))
    return 0 if result['status'] == 'certified_safety_only' else 1


if __name__ == '__main__':
    sys.exit(main())
