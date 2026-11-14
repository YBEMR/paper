"""Fetch immutable public inputs for audit.py; never import or execute downloads."""
import hashlib,json,urllib.parse,urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT=Path(__file__).resolve().parent
entries=[]
for name in ['source_manifest.json','auxiliary_manifest.json']:
    entries.extend(json.loads((ROOT/name).read_text(encoding='utf-8')))
def fetch(e):
    dest=(ROOT/e['local_path']).resolve()
    assert dest.is_relative_to(ROOT/'source_cache')
    if dest.exists() and hashlib.sha256(dest.read_bytes()).hexdigest()==e['sha256']:
        return
    url=f"https://raw.githubusercontent.com/{e['repository']}/{e['revision']}/{urllib.parse.quote(e['path'],safe='/')}"
    with urllib.request.urlopen(url,timeout=30) as r:
        raw=r.read(e['bytes']+1)
    assert len(raw)==e['bytes'] and hashlib.sha256(raw).hexdigest()==e['sha256'],e['path']
    assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==e['git_blob_sha']
    dest.parent.mkdir(exist_ok=True)
    dest.write_bytes(raw)
with ThreadPoolExecutor(max_workers=4) as pool:
    list(pool.map(fetch,entries))
dest=ROOT/'external_sources/BatchDVFS_results.zip'
expected='c970f91a241be7129b0770686dd3198c9224d6a8ba7143d62eb6a3f490729d19'
if not dest.exists() or hashlib.sha256(dest.read_bytes()).hexdigest()!=expected:
    url='https://raw.githubusercontent.com/nabavinejad/BatchDVFS/f05286df4b228ac18d5e83c0e3d8a153d5a5c5fc/BatchDVFS/Results/Results_JournalPaper_BatchDVFS.zip'
    with urllib.request.urlopen(url,timeout=30) as r:
        raw=r.read(756587)
    assert len(raw)==756586 and hashlib.sha256(raw).hexdigest()==expected
    dest.parent.mkdir(exist_ok=True)
    dest.write_bytes(raw)
print('Verified 85 source files and one fixed result archive. No downloaded code executed.')
