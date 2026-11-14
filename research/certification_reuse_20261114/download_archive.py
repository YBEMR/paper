"""Optional byte retrieval only: immutable user-specified public GitHub commit."""
import argparse, concurrent.futures, hashlib, json, urllib.request
from pathlib import Path

def main(cache):
    manifest=json.loads(Path(__file__).with_name('source_manifest.json').read_text(encoding='utf-8'))
    def fetch(item):
        target=cache/item['path']
        data=target.read_bytes() if target.exists() else b''
        if hashlib.sha256(data).hexdigest()!=item['sha256']:
            url=f"https://raw.githubusercontent.com/YBEMR/paper/{manifest['commit']}/{item['path']}"
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'readonly-certification-audit'}),timeout=60) as response:
                data=response.read(45_000_001)
            if len(data)>45_000_000: raise RuntimeError('per-file bound exceeded')
            if hashlib.sha256(data).hexdigest()!=item['sha256']: raise RuntimeError('source hash mismatch: '+item['path'])
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==item['sha']
        return len(data)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: sizes=list(pool.map(fetch,manifest['sources']))
    print(json.dumps({'files':len(sizes),'bytes':sum(sizes),'source_code_executed':False}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cache',required=True,type=Path);main(p.parse_args().cache)
