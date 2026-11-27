"""Lossless archive. Restore plan/certificate pairs and the original 31-column event arrays."""
import argparse,gzip,io,json,lzma,tarfile,tempfile
from pathlib import Path
import numpy as np
from shared import HERE,RUN,sha,read,put

def npbytes(arr):
    f=io.BytesIO();np.save(f,arr,allow_pickle=False);return f.getvalue()
def add(tar,name,data):
    info=tarfile.TarInfo(name);info.size=len(data);tar.addfile(info,io.BytesIO(data))
def prediction(base,ticks):
    where=np.searchsorted(base[:,0],ticks)
    return np.ascontiguousarray(base[np.clip(where,0,len(base)-1)]).view(np.uint64)
def encode(base,arr):
    ticks=arr[:,0].astype('<i8')
    assert np.array_equal(arr[:,0],ticks)
    return ticks,np.bitwise_xor(np.ascontiguousarray(arr).view(np.uint64),prediction(base,ticks))
def decode(base,ticks,words):
    return np.bitwise_xor(words,prediction(base,ticks)).view(np.float64)
def pack(case):
    root=RUN/case
    dest=HERE/'archive';dest.mkdir(exist_ok=True)
    target=dest/(case+'.tar.xz')
    seen=set();physical={}
    with np.load(RUN/'preflight'/case/'original_events.npz') as data:base=data['events']
    with lzma.open(target,'wb',preset=4) as compressed,tarfile.open(fileobj=compressed,mode='w|') as tar:
        add(tar,'baseline.npy',npbytes(base))
        for arm in sorted(root.iterdir()):
            if not arm.is_dir():continue
            for receipt_file in sorted(arm.glob('*.json*')):add(tar,arm.name+'/'+receipt_file.name,receipt_file.read_bytes())
            for path in sorted((arm/'physical/certificates').glob('*.json')):
                key=path.stem
                raw=gzip.decompress((arm/'physical/plans'/(key+'.json.gz')).read_bytes())
                cert=path.read_bytes();assert sha(raw)==key and json.loads(cert)['plan']==key
                with np.load(path.with_suffix('.npz')) as data:arr=data['events']
                sign=[sha(raw),sha(cert),sha(arr.tobytes())]
                if key in seen:
                    assert physical[key]==sign;continue
                seen.add(key);physical[key]=sign
                ticks,words=encode(base,arr)
                assert np.array_equal(decode(base,ticks,words).view(np.uint64),arr.view(np.uint64))
                for name,body in [('plan.json',raw),('certificate.json',cert),('ticks.npy',npbytes(ticks)),('xor.npy',npbytes(words.T.copy()))]:
                    add(tar,key+'/'+name,body)
        add(tar,'hashes.json',json.dumps(physical,sort_keys=True,separators=(',',':')).encode())
    return dict(file=target.name,size=target.stat().st_size,sha256=sha(target.read_bytes()),physical=len(seen))
def restore(source,dest=None):
    # Tar content is read as data. All output paths are restricted to validated plan hashes.
    expected={};actual={}
    if not source.is_file():
        index=read(source.with_name(source.name+'.parts.json'))
        with tempfile.TemporaryDirectory() as tmp:
            combined=Path(tmp)/source.name
            with combined.open('wb') as stream:
                for part in index['parts']:
                    filename=part['name']
                    assert Path(filename).name==filename
                    data=(source.parent/filename).read_bytes()
                    assert sha(data)==part['sha256']
                    stream.write(data)
            assert sha(combined.read_bytes())==index['sha256']
            return restore(combined,dest)
    with tarfile.open(source,'r|xz') as tar:
        for member in tar:
            b=tar.extractfile(member).read();parts=member.name.split('/')
            if member.name=='baseline.npy':base=np.load(io.BytesIO(b),allow_pickle=False)
            elif member.name=='hashes.json':expected=json.loads(b)
            elif len(parts)==2 and len(parts[0])==64:
                key,kind=parts
                if any(c not in '0123456789abcdef' for c in key):raise ValueError(key)
                folder=(dest/key) if dest else None
                if folder:folder.mkdir(parents=True,exist_ok=True)
                if kind=='plan.json':
                    assert sha(b)==key;actual[key]=[key]
                elif kind=='certificate.json':actual[key].append(sha(b))
                elif kind=='ticks.npy':ticks=np.load(io.BytesIO(b),allow_pickle=False)
                elif kind=='xor.npy':
                    words=np.load(io.BytesIO(b),allow_pickle=False).T
                    arr=decode(base,ticks,words);actual[key].append(sha(arr.tobytes()))
                    if folder:np.savez_compressed(folder/'events.npz',events=arr)
                if folder and kind.endswith('.json'):(folder/kind).write_bytes(b)
            elif dest and len(parts)==2 and parts[0] in ('A','B','C','D','diagnostic') and Path(parts[1]).name==parts[1]:
                path=dest/parts[0]/parts[1];path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b)
    assert actual==expected and actual
    return len(actual)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['pack','restore','verify']);parser.add_argument('case');parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.action=='pack':
        rec=pack(args.case);source=HERE/'archive'/rec['file'];assert restore(source)==rec['physical']
        put(HERE/'archive'/(args.case+'.json'),rec);print(rec)
    else:print(restore(HERE/'archive'/(args.case+'.tar.xz'),args.output if args.action=='restore' else None))
