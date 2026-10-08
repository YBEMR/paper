"""Read-only schedule/accounting checks; no thermal replays or search."""
from pathlib import Path
from fractions import Fraction as F
import argparse
import run as r
a=r.a;w=r.w


def check(folder):
    checks=[]
    def ck(name,ok):checks.append(dict(name=name,passed=bool(ok)))
    records=[a.old.read(folder/f'{i:02d}.json') for i in range(28)]
    ck('28_tasks_fixed_order',[v['task'] for v in records]==r.tasks())
    ck('sources_match',a.old.read(folder/'hashes.json')==r.identities())
    for i,rec in enumerate(records):
        t=rec['task'];v=rec['result'];elapsed=F(rec['evaluation_elapsed_s'])
        valid_U=v.get('certified_candidate_energy',{}).get('status')=='available'
        ck(str(i)+'_late_no_score',elapsed<=20 or ('score_J' not in v and not valid_U))
        if t['kind']!='full':continue
        b=a.bundle(a.load(),t['a'],t['b'])
        if 'binding' in v:ck(str(i)+'_binding',v['binding']==w.binding(b))
        traces=v.get('finite_path_energy',{}).get('traces',v.get('partial_traces',{}))
        for path in b['evaluation']['paths']:
            tid=path['trace']['id'];got=traces.get(tid)
            if not got:continue
            rows,_,_,failure=a.v1.expand(b['candidate'],path['trace'],a.v2.Budget(seconds=20))
            def key(row):return tuple(row[k] for k in ['mode','stage','unit','opp'])+(F(row['start_us']),F(row['end_us']))
            ck(str(i)+tid+'_schedule',list(map(key,rows))==list(map(key,got['schedule'])))
            ck(str(i)+tid+'_no_deadline_failure',not failure)
            tr=got.get('thermal',{})
            if not tr.get('complete') or 'energy_J' not in tr:continue
            ck(str(i)+tid+'_full_80ms',F(tr['covered_until_us'])==80000)
            parts=sum((w.I(*v) for k in ['base_by_node_J','activity_by_node_J'] for v in tr[k]),w.I(0))+w.I(*tr['external_J'])+w.I(*tr['leakage_J'])
            ck(str(i)+tid+'_energy_accounting',a.old.overlap(parts,w.I(*tr['energy_J'])))
            if got.get('rankable_energy'):
                ck(str(i)+tid+'_safe_upper',all(F(z[1])<=F(limit) for z,limit in zip(tr['peak_C'],b['candidate']['platform']['temperature_limit_C'])))
    summary=r.summarize(records)
    ck('summary_recomputed',a.joint.digest(summary)==a.joint.digest(a.old.read(folder/'summary.json')))
    return dict(passed=all(c['passed'] for c in checks),checks=checks,scope='posthoc recorded evidence only; no thermal replay')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder');args=p.parse_args();folder=Path(args.folder)
    out=folder/'postcheck.json'
    if out.exists():raise FileExistsError(out)
    result=check(folder);a.old.write(out,result);print(sum(v['passed'] for v in result['checks']),len(result['checks']))
    raise SystemExit(0 if result['passed'] else 1)
