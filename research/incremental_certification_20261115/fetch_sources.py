"""Download immutable public GitHub inputs; no simulation or search."""
import argparse,hashlib,json,urllib.request
from pathlib import Path

def verify(data,row):
    return (len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256'] and
            hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==row['git_blob'])

def main(cache,check_only):
    manifest=json.loads(Path(__file__).with_name('source_manifest.json').read_text(encoding='utf-8'))
    for row in manifest['sources']:
        target=cache/row['path']
        if target.exists():
            if not verify(target.read_bytes(),row):raise RuntimeError('SOURCE_MISMATCH:'+row['path'])
        elif check_only:raise FileNotFoundError(target)
        else:
            url='https://raw.githubusercontent.com/YBEMR/paper/'+manifest['commit']+'/'+row['path']
            data=urllib.request.urlopen(url,timeout=120).read()
            if not verify(data,row):raise RuntimeError('DOWNLOAD_MISMATCH:'+row['path'])
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    print(json.dumps({'verified':len(manifest['sources']),'commit':manifest['commit'],'mode':'read-only verification' if check_only else 'verified fetch'}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cache',required=True,type=Path);p.add_argument('--check-only',action='store_true')
    a=p.parse_args();main(a.cache,a.check_only)
