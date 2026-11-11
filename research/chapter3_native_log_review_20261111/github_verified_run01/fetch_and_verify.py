"""Read the immutable published ZIP; never import or execute research code."""
import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import subprocess
import time
import zipfile

HERE = Path(__file__).resolve().parent
REVIEW = HERE.parent
COMMIT = '2fc52c63814d06b039e24a3bde887a2b411be298'
REL = 'research/r1_native_local_results_20261110/run01/R1_native_pair_20261110_run01_results.zip'
URL = f'https://raw.githubusercontent.com/YBEMR/paper/{COMMIT}/{REL}'
EXPECTED = 'b0aab1f9d62df45634400a45b526fc5a8652eaa9d4ef594270df20f7998a79f1'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def save(name, data):
    path = HERE / name
    with path.open('x', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')

def main():
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    t = time.monotonic()
    archive = HERE / 'R1_native_pair_20261110_run01_results.zip'
    raw = HERE / 'raw'
    if archive.exists() or raw.exists():
        raise RuntimeError('Refusing to overwrite existing downloaded evidence')
    protected = {str(p.relative_to(REVIEW)): digest(p) for p in REVIEW.rglob('*')
                 if p.is_file() and HERE not in p.parents}
    save('protected_review_files.json', protected)
    cmd = ['curl', '--fail', '--silent', '--show-error', '--location', '--max-time', '60',
           '--output', str(archive), URL]
    p = subprocess.run(cmd, capture_output=True, text=True)
    save('download_record.json', dict(started_utc=started, argv=cmd, returncode=p.returncode,
                                    stderr=p.stderr, source_commit=COMMIT, source_path=REL))
    if p.returncode:
        raise RuntimeError('Download failed; see download_record.json')
    got = digest(archive)
    if got != EXPECTED:
        raise RuntimeError(f'Archive SHA256 mismatch: {got}')
    members = []
    with zipfile.ZipFile(archive) as z:
        if sum(i.file_size for i in z.infolist()) > 1024**3:
            raise RuntimeError('Archive uncompressed size exceeds one GiB')
        seen = set()
        for i in z.infolist():
            name = i.filename
            path = PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
                raise RuntimeError(f'Unsafe archive path: {name!r}')
            if stat.S_ISLNK(i.external_attr >> 16) or name in seen:
                raise RuntimeError(f'Symlink or duplicate archive member: {name!r}')
            seen.add(name)
            if not i.is_dir():
                data = z.read(i)
                target = raw.joinpath(*path.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('xb') as f:
                    f.write(data)
                members.append(dict(path=name, bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
    save('zip_member_manifest.json', members)
    save('fetch_completion.json', dict(started_utc=started,
        ended_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        elapsed_s=time.monotonic()-t, sha256=got, bytes=archive.stat().st_size,
        member_files=len(members), uncompressed_bytes=sum(x['bytes'] for x in members),
        new_solver_build_thermal_calls=0, protected_file_count=len(protected)))
    print(json.dumps(json.loads((HERE/'fetch_completion.json').read_text()), indent=2))

if __name__ == '__main__':
    main()
