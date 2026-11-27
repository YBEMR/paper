"""Compare historical event matrices with the two exact-seed replays on this host."""
import csv,gzip,io,tarfile
import numpy as np
from shared import *
def main():
    out=[];ext=Path(os.environ.get('E3_SOURCES',THREE.parent))
    for case in ['D1','D2','C10']:
        key=read(DATA/case/'identity.json')['historical_plan']
        replay_file=RUN/'preflight'/case/'original_events.npz'
        with np.load(replay_file) as data:arr=data['events']
        if case=='C10':
            index=next((NT/'research/m1i_generalization/data/evidence').glob('C10*/event_index.csv.gz'))
            with gzip.open(index,'rt') as f:
                row=next(x for x in csv.DictReader(f) if x['plan']==key)
            expected=row['event_array_sha256'];source=index.name
            assert sha(arr.tobytes())==expected
            original=arr
        else:
            folder=ext/'fourth/research/chapter4_cross_analysis_v5_execution/checkpoints/windows_26200/archive'
            archive=b''.join(z.read_bytes() for z in sorted(folder.glob(case+'.0*')))
            with tarfile.open(fileobj=io.BytesIO(archive),mode='r|xz') as tar:
                stream=iter(tar);m=next(stream);index=json.load(tar.extractfile(m))
                source=next(k for k in index if k.endswith(key+'.npz'));meta=index[source]
                m=next(x for x in stream if x.name.split('/')[-1]==meta['sha256'])
                raw=tar.extractfile(m).read();original=np.load(io.BytesIO(raw),allow_pickle=False)
                if meta['encoding']=='raw':original=original['events']
                expected=sha(original.tobytes())
        actual=sha(arr.tobytes());assert np.array_equal(arr[:,:14],original[:,:14])
        delta=np.max(np.abs(arr-original),axis=0);assert max(delta)<1e-8
        np.savez_compressed(DATA/case/'original_events.npz',events=original)
        out.append(dict(case=case,source=source,archived_plan=key,shape=arr.shape,archived_event_sha256=expected,
                        replayed_event_sha256=actual,full_bitwise=actual==expected,first_14_columns_exact=True,
                        max_absolute_by_column=delta.tolist()))
    put(HERE/'results'/'original_trace_identity.json',out)
if __name__=='__main__':main()
