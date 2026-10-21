"""Hash local evidence and prepare an explicit Git path list. No research calls."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess

OUT = Path(__file__).resolve().parents[1]
REPO = next(p for p in OUT.parents if (p / 'AGENTS.md').is_file())
MANIFEST = OUT / 'archive_inventory.json'


def main():
    paths = sorted(p.relative_to(REPO).as_posix() for p in OUT.rglob('*')
                   if p.is_file() and p != MANIFEST)
    proc = subprocess.run(['git', 'check-ignore', '--stdin', '-z'], cwd=REPO,
                          input=('\0'.join(paths) + '\0').encode(), capture_output=True)
    assert proc.returncode in (0, 1), proc.stderr
    ignored = set(proc.stdout.decode().rstrip('\0').split('\0')) if proc.stdout else set()
    patterns = [rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
                rb'\bgh[pousr]_[A-Za-z0-9]{20,}', rb'\bgithub_pat_[A-Za-z0-9_]{30,}',
                rb'\bsk-proj-[A-Za-z0-9_-]{20,}']
    hits, rows = [], []
    for name in paths:
        data = (REPO / name).read_bytes()
        is_ignored = name in ignored
        if not is_ignored and any(re.search(pattern, data) for pattern in patterns):
            hits.append(name)
        rows.append({'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                     'ignored_by_git': is_ignored})
    assert not hits, ('Credential-like content requires review, paths only', hits)
    assert len(ignored) == 40 and all(Path(name).suffix == '.mat' for name in ignored)
    assert max(row['bytes'] for row in rows if not row['ignored_by_git']) < 100 * 2**20
    payload = {'protocol': 'K156-local-evidence-archive-v1', 'files': rows,
               'files_count': len(rows), 'total_local_bytes': sum(row['bytes'] for row in rows),
               'git_ignored_count': len(ignored), 'git_ignored_extensions': dict(Counter(Path(p).suffix for p in ignored)),
               'credential_pattern_scan_passed': True, 'research_calls': 0, 'new_thermal_evaluations': 0,
               'scope': 'Local includes ignored MAT hashes. Manifest excludes its own bytes. No force-add.'}
    with MANIFEST.open('x', encoding='utf-8') as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    selected = [name for name in paths if name not in ignored]
    selected += [MANIFEST.relative_to(REPO).as_posix(), 'RESEARCH_BRIEF.md',
                 'research/03_证据与检索记录.md', 'research/第三章当前进展与正式实验推进计划_审查稿.md',
                 'research/chapter3_experiments/results/p0_resume_claim01.json']
    selected = sorted(set(selected))
    pathlist = REPO / '.runtime/k156_stage_paths.txt'
    pathlist.write_text('\n'.join(selected) + '\n', encoding='utf-8')
    (REPO / '.runtime/k156_stage_paths.json').write_text(json.dumps(selected, ensure_ascii=False), encoding='utf-8')
    print({'local_files': len(rows), 'selected_paths_including_unchanged': len(selected),
           'local_MiB': round(payload['total_local_bytes']/2**20, 2),
           'ignored_MAT_count': len(ignored), 'credential_scan': 'PASS', 'explicit_pathspec': str(pathlist)})


if __name__ == '__main__':
    main()
