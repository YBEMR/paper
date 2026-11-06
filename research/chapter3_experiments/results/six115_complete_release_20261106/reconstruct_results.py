"""Reassemble and verify complete sanitized JSON results; no experiments run."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

def sha(data):
    return hashlib.sha256(data).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('reconstructed_six115'))
    args=parser.parse_args()
    root=Path(__file__).resolve().parent
    entries=json.loads((root/'raw/index.json').read_text(encoding='utf-8'))
    destination=args.output.resolve()
    for entry in entries:
        chunks=[]
        for part in entry['parts']:
            path=(root/part['path']).resolve()
            if not path.is_relative_to(root):raise ValueError('Invalid part path')
            value=path.read_bytes()
            if len(value)!=part['bytes'] or sha(value)!=part['sha256']:raise ValueError('Part checksum mismatch: '+part['path'])
            chunks.append(value)
        compressed=b''.join(chunks)
        if len(compressed)!=entry['gzip_bytes'] or sha(compressed)!=entry['gzip_sha256']:raise ValueError('Gzip checksum mismatch')
        value=gzip.decompress(compressed)
        if len(value)!=entry['sanitized_json_bytes'] or sha(value)!=entry['sanitized_json_sha256']:raise ValueError('JSON checksum mismatch')
        json.loads(value)
        target=(destination/entry['job']/(entry['kind']+'_result.json')).resolve()
        if not target.is_relative_to(destination):raise ValueError('Invalid output path')
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as f:f.write(value)
        print(entry['job'],entry['kind'],len(value),sha(value))
    print('Verified and reconstructed',len(entries),'complete result JSON files. No scientific computation executed.')

if __name__=='__main__':main()
