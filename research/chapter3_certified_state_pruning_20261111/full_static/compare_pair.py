"""Read-only semantic comparison of completed static pair exports; never solve."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import numpy as np

HERE=Path(__file__).resolve().parent
ARCHIVE=HERE.parents[2]/'research/chapter3_support_autol_lp_20261111/autol_build/rev02/execution/on'
read=lambda p:json.loads(p.read_text())

def load(folder):
    with np.load(folder/'exported_model.npz',allow_pickle=False) as source:
        arrays={name:source[name] for name in source.files}
    return dict(folder=folder,arrays=arrays,names=read(folder/'variable_names.json'),
                tags=read(folder/'row_tags.json'),result=read(folder/'result.json'))

def same_array(left,right):
    return left.dtype==right.dtype and left.shape==right.shape and left.tobytes()==right.tobytes()

def signatures(model,deleted,drop_deleted_physics):
    names=model['names'];m=model['arrays'];counts=Counter();dropped=Counter()
    for meta in model['tags']:
        family=meta['tag'].split('/')[0]
        if family=='energy_state_lower_bound':
            dropped['energy_cut_separately_certified']+=1;continue
        if drop_deleted_physics and meta['gate_name'] in deleted:
            assert family in ['thermal_propagation','complete_energy']
            dropped[family]+=1;continue
        row=meta['index'];start,end=int(m['A_indptr'][row]),int(m['A_indptr'][row+1])
        entries=sorted((names[int(j)],float(value).hex())
            for j,value in zip(m['A_indices'][start:end],m['A_data'][start:end])
            if names[int(j)] not in deleted)
        canonical=json.dumps([meta['tag'],entries,float(m['b'][row]).hex()],separators=(',',':'))
        digest=hashlib.sha256(canonical.encode()).hexdigest()
        counts[meta['tag'],digest]+=1
    return counts,dropped

def main():
    began=datetime.now(timezone.utc).isoformat();start=time.monotonic()
    assert (HERE/'batch_completed.json').exists(), 'No complete pair'
    off=load(HERE/'execution/off');on=load(HERE/'execution/on')
    assert off['result']['success'] and on['result']['success']
    with np.load(ARCHIVE/'exported_model.npz',allow_pickle=False) as archive:
        archive_equal={name:same_array(off['arrays'][name],archive[name]) for name in archive.files}
    assert all(archive_equal.values()),archive_equal
    assert off['names']==read(ARCHIVE/'variable_names.json')
    assert read(off['folder']/'options.json')==read(on['folder']/'options.json')
    assert off['result']['events']==on['result']['events']
    deleted=set(off['names'])-set(on['names']);added=set(on['names'])-set(off['names'])
    assert not added and all(name.startswith('w:') for name in deleted)
    indexes={name:i for i,name in enumerate(off['names'])};vectors={}
    for key in ['lb','ub','c']:
        before=off['arrays'][key][[indexes[name] for name in on['names']]]
        vectors[key]=same_array(before,on['arrays'][key])
    assert all(vectors.values()),vectors
    intnames=lambda data:{data['names'][int(j)] for j in data['arrays']['intcon']}
    assert intnames(off)==intnames(on)
    before,dropped=signatures(off,deleted,True);after,_=signatures(on,set(),False)
    missing=before-after;extra=after-before
    assert not missing and not extra, ('SURVIVING_NUMERICAL_ROWS_DIFFER',len(missing),len(extra))
    assert dropped['thermal_propagation']==8*len(deleted)
    assert dropped['complete_energy']==2*len(deleted)
    for data in [off,on]:
        checks=read(data['folder']/'energy_certificate_checks.json')
        assert len(checks)==424 and all(c['passed'] for c in checks)
    result=dict(started_utc=began,ended_utc=datetime.now(timezone.utc).isoformat(),wall_s=time.monotonic()-start,
        off_archive_arrays_byte_equal=archive_equal,off_archive_names_equal=True,
        options_equal=True,events_equal=True,shared_variable_vectors_byte_equal=vectors,
        original_integer_variable_names_equal=True,removed_names=sorted(deleted),removed_w=len(deleted),
        removed_row_families=dict(dropped),surviving_non_cut_row_multiset_exact=True,
        surviving_row_instances=sum(after.values()),new_energy_cuts_exact_box_certified=True,
        off_counts={k:off['result'][k] for k in ['variables','rows','nonzeros','joint_state_blocks','build_s','export_s','worker_elapsed_s']},
        on_counts={k:on['result'][k] for k in ['variables','rows','nonzeros','joint_state_blocks','build_s','export_s','worker_elapsed_s']},
        scope='Exact binary64 name-based row comparison after deleted w=0 substitution; energy cuts separately certified. Full LP relaxation need not match; no solver speedup claim.',
        new_static_builds=0,new_solver_calls=0,new_thermal_calls=0)
    with (HERE/'comparison.json').open('x') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k!='removed_names'},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
