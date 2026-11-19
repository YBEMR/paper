"""Create/check an explicit source manifest; this never runs an experiment."""
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = '02f3f621cc9ce7f1cd991577388343fa906bbf56'
INHERITED = [
    'research/kim_case_b_freeze/input.json',
    'research/kim_safety_repair_audit/design.py',
    'research/kim_safety_repair_audit/design.json',
    'research/kim_safety_repair_audit/raw/new/results.json',
    'research/kim_scene_dvfs_admission/run.py',
    'research/kim_scene_dvfs_admission/protocol.json',
    'research/kim_scene_dvfs_admission/joint_thermal.py',
    'research/kim_scene_dvfs_admission/scene_events.py',
    'research/kim_synthetic_platform_v1/events.py',
    'research/kim_synthetic_platform_v1/profiles.py',
    'research/kim_synthetic_platform_v1/thermal.py',
    'research/kim_synthetic_platform_v1/workloads.py',
    'research/kim_synthetic_platform_v1/platform.json',
    'research/kim_synthetic_platform_v1/experiments.json',
    'research/kim_thermal_v1/physics.py',
]
NEW = [
    'ac_closure.py', 'catalog.py', 'experiment.py', 'test_expansion.py', 'freeze.py',
    'catalog.json', 'expanded_input.json', 'legality.csv', 'stage_features.csv',
    'protocol.md', 'sources.md', 'baseline_sources.json',
    'sources/jedi_yolov3.cfg', 'sources/source_manifest.json',
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    proof = json.loads((HERE / 'baseline_sources.json').read_text(encoding='utf8'))
    if proof['commit'] != BASE:
        raise ValueError('Wrong remote frozen source')
    remote = {item['path']: item['git_blob_sha1'] for item in proof['files']}
    for relative in INHERITED:
        data = (ROOT / relative).read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if remote.get(relative) != actual:
            raise ValueError('Remote-source content mismatch: ' + relative)
    paths = INHERITED + [(HERE / name).relative_to(ROOT).as_posix() for name in NEW]
    manifest = dict(base_commit=BASE, files={p: digest(ROOT / p) for p in sorted(paths)},
                    cases_ac=4, cases_expanded=4, ac_case_cap_s=120,
                    expanded_case_cap_s=300, planned_max_case_seconds=1680,
                    authority='User direct task instruction, 2026-11-19; not external agent_loop approval')
    (HERE / 'freeze_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf8')
    return manifest


def verify():
    manifest = json.loads((HERE / 'freeze_manifest.json').read_text(encoding='utf8'))
    if manifest['base_commit'] != BASE:
        raise ValueError('Wrong baseline')
    for p, expected in manifest['files'].items():
        if digest(ROOT / p) != expected:
            raise ValueError('Frozen source changed: ' + p)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--create', action='store_true')
    args = parser.parse_args()
    manifest = build() if args.create else verify()
    print(json.dumps(dict(status='PASS', files=len(manifest['files']),
                          manifest_sha256=digest(HERE / 'freeze_manifest.json'))))
