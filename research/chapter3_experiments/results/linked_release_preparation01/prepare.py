"""K174 pure option-label audit, never a production selector or candidate evaluator."""
import argparse
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import runpy
import sys
import time

HERE=Path(__file__).resolve().parent
BASE=HERE.parents[1]
ROOT=BASE.parents[1]
READS={}
GUARD={'scientific_import':0,'production_entry':0,'process_or_network':0}
RULE='slower-cheaper-closed-retiming-with-open-conflict-v1'

def digest(raw):return hashlib.sha256(raw).hexdigest()
def canonical(obj):return digest(json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode())
def read(p):
    p=Path(p);raw=p.read_bytes();READS[p.relative_to(ROOT).as_posix()]=digest(raw)
    return json.loads(raw)
def audit(event,args):
    if event=='import' and args[0].split('.')[0] in {'numpy','scipy','matlab','thermal','milp','inputs','schedules','scene_adapter','linked_method','neighborhood_method','linked_neighborhood','anchor_preelimination'}:
        GUARD['scientific_import']+=1;raise RuntimeError('No scientific imports')
    if event in {'subprocess.Popen','os.system','socket.connect','socket.getaddrinfo'} or event.startswith('os.spawn'):
        GUARD['process_or_network']+=1;raise RuntimeError('No process/network actions')
def profile(frame,event,arg):
    name=frame.f_code.co_filename.replace('\\','/')
    if event=='call' and '/research/chapter3_experiments/' in name and '/results/' not in name:
        GUARD['production_entry']+=1;raise RuntimeError('No production entry')

def conflict(a,b,edges):
    overlap=max(F(a['start_ms']),F(b['start_ms']))<min(F(a['end_ms']),F(b['end_ms']))
    reasons=[]
    if overlap and a['unit_id']==b['unit_id']:reasons.append('same_unit')
    if overlap and a['domain_id']==b['domain_id'] and a['opp_id']!=b['opp_id']:reasons.append('same_domain_different_opp')
    if (a['stage_id'],b['stage_id']) in edges and F(a['end_ms'])>F(b['start_ms']):reasons.append('predecessor')
    if (b['stage_id'],a['stage_id']) in edges and F(b['end_ms'])>F(a['start_ms']):reasons.append('successor')
    return reasons

def view(instance,scene,warm,opened):
    stages={s['id']:s for s in scene['stage_instances']}
    if len(stages)!=len(scene['stage_instances']) or set(warm)!=set(stages):raise ValueError('Stage identity mismatch')
    if not set(opened)<set(stages) or not opened or len(opened)!=len(set(opened)):raise ValueError('Need nonempty proper mask')
    requests={r['id']:r for r in scene['requests']}
    edges={tuple(x) for x in scene['dependencies']}
    if any(len(e)!=2 or not set(e)<=set(stages) for e in edges):raise ValueError('Unknown edge')
    catalog={};anchors={};minimum={}
    for k,s in stages.items():
        choices={m['opp_id']:m for m in instance['stage_modes'][s['shared_stage_id']] if m['unit_id']==warm[k]['unit']}
        if len(choices)!=sum(m['unit_id']==warm[k]['unit'] for m in instance['stage_modes'][s['shared_stage_id']]):raise ValueError('Ambiguous mode')
        for m in choices.values():
            if F(m['duration_ms'])<=0 or F(m['activity_energy_J'])!=F(m['activity_power_W'])*F(m['duration_ms'])/1000:raise ValueError('Invalid physical mode ledger')
        m=choices[warm[k]['opp']];start=F(warm[k]['start_ms'])
        if start<0 or start%F(instance['start_grid_ms']):raise ValueError('Anchor outside grid')
        catalog[k]=choices;minimum[k]=min(F(m['duration_ms']) for m in choices.values())
        anchors[k]={'stage_id':k,'unit_id':m['unit_id'],'domain_id':m['domain_id'],'opp_id':m['opp_id'],'start_ms':str(start),'end_ms':str(start+F(m['duration_ms']))}
    order=[];pending=set(stages)
    while pending:
        ready=sorted(k for k in pending if not any(v==k and u in pending for u,v in edges))
        if not ready:raise ValueError('Cyclic DAG')
        order+=ready;pending-=set(ready)
    # Optimistic same-device shortest-duration paths. Resources and heat relaxed.
    earliest={};latest_finish={}
    for k in order:
        req=requests[stages[k]['request_id']]
        earliest[k]=max([F(req['release_ms'])]+[earliest[u]+minimum[u] for u,v in edges if v==k])
    for k in reversed(order):
        req=requests[stages[k]['request_id']]
        latest_finish[k]=min([F(instance['window_ms']),F(req['deadline_ms'])]+[latest_finish[v]-minimum[v] for u,v in edges if u==k])
    return stages,edges,catalog,anchors,earliest,latest_finish

def select_scene(instance,scene,warm,opened):
    stages,edges,modes,anchors,earliest,latest=view(instance,scene,warm,opened)
    closed=sorted(set(stages)-set(opened));triggers=[];rejected=[]
    if len(closed)<=1:return {'selected':None,'opened':sorted(opened),'triggers':[],'reason':'keep_one_closed_stage'}
    if F(scene['weight'])<=0:return {'selected':None,'opened':sorted(opened),'triggers':[],'reason':'no_positive_objective_weight'}
    for j in closed:
        current=modes[j][warm[j]['opp']]
        for opp,m in sorted(modes[j].items()):
            saving=F(current['activity_energy_J'])-F(m['activity_energy_J'])
            if saving<=0 or F(m['duration_ms'])<=F(current['duration_ms']):continue
            d=F(m['duration_ms']);oldstart=F(warm[j]['start_ms'])
            upper=min([latest[j]]+[F(anchors[v]['start_ms']) for u,v in edges if u==j and v in closed and v!=j])
            lower=max([earliest[j]]+[F(anchors[u]['end_ms']) for u,v in edges if v==j and u in closed and u!=j])
            if oldstart+d<=upper:continue
            grid=F(instance['start_grid_ms']);first=max(0,-((-lower)//grid));last=(upper-d)//grid
            labels=[]
            for n in range(first,last+1):
                start=n*grid
                row={'stage_id':j,'unit_id':m['unit_id'],'domain_id':m['domain_id'],'opp_id':opp,'start_ms':str(start),'end_ms':str(start+d)}
                if any(conflict(row,anchors[k],edges) for k in closed if k!=j):continue
                blockers={k:conflict(row,anchors[k],set()) for k in sorted(opened)}
                blockers={k:v for k,v in blockers.items() if v}
                labels.append({'label':row,'open_anchor_resource_conflicts':blockers})
            # Strong trigger: every necessary-feasible start requires moving an
            # existing open anchor. No complete assignment is generated or proved.
            if not labels or any(not x['open_anchor_resource_conflicts'] for x in labels):
                rejected.append({'stage_id':j,'opp':opp,'reason':'no_labels_or_unblocked_retiming_exists','necessary_label_count':len(labels)})
                continue
            triggers.append({'stage_id':j,'target_opp':opp,'unit_id':m['unit_id'],'old_start_ms':str(oldstart),
                'old_activity_energy_J':current['activity_energy_J'],'new_activity_energy_J':m['activity_energy_J'],
                'activity_saving_proxy_J':str(saving),'weighted_proxy_J':str(F(scene['weight'])*saving),
                'earliest_ms':str(lower),'latest_start_ms':str(upper-d),'last_grid_start_ms':str(last*grid),
                'old_start_new_end_ms':str(oldstart+d),'latest_finish_ms':str(upper),'necessary_labels':labels})
    triggers.sort(key=lambda t:(-F(t['weighted_proxy_J']),t['stage_id'],t['target_opp']))
    selected=triggers[0]['stage_id'] if triggers else None
    return {'selected':selected,'opened':sorted(set(opened)|({selected} if selected else set())),
        'triggers':triggers,'rejected':rejected,'reason':'triggered' if selected else 'no_trigger'}

def run(out):
    out=Path(out)
    if out.exists():raise FileExistsError('Append-only preparation')
    t=time.perf_counter();helper=BASE/'results/bound_build_replay01/domain/extract_domains.py'
    READS[helper.relative_to(ROOT).as_posix()]=digest(helper.read_bytes())
    h=runpy.run_path(str(helper))
    records=[]
    for case in ('base__R1','base__R3'):
        folder=BASE/'results/linked_ablation_execution01/calls'/ (case+'__C')
        r=read(folder/'result.json');i=read(folder/'input_instance.json');a=read(folder/'audit.json');post=read(folder/'post_audit.json')
        if not a['passed'] or not post['passed']:raise ValueError('Original evidence not admitted')
        c=r['phases'][1]['condition']
        if c['source_input_sha256']!=canonical(i) or c['warm_candidate_sha256']!=canonical(c['warm_candidate']) or c['warm_receipt']['state']!='SAFE':raise ValueError('S1 identity')
        for scene in i['scenarios']:
            sid=scene['id'];old=c['opened_by_scene'][sid];warm=c['warm_options_by_scene'][sid]
            record=select_scene(i,scene,warm,old)
            # Reuse K171 pure exact transcription to recount all Stage options.
            # It does not import or execute the original matrix constructor.
            raw=h['original_options'](i,sid,c['shared_deployment'])
            def count(mask):
                cc=deepcopy(c);cc['opened_by_scene'][sid]=mask
                opts,_=h['neighborhood_options'](i,cc,raw,2)
                opts=[o for o in opts if F(o['end_ms'])<=F(o['request_deadline_ms'])]
                retained,stats=h['anchor_options'](i,cc,sid,opts)
                return retained,stats
            old_rows,oldstats=count(old);new_rows,newstats=count(record['opened'])
            ident=lambda o:(o['stage_instance_id'],o['unit_id'],o['opp_id'],o['start_ms'])
            oldset=set(map(ident,old_rows));newset=set(map(ident,new_rows))
            archived=r['phases'][1]['scenes'][sid]['model_summary']['options']
            if len(old_rows)!=archived or not oldset<=newset:raise ValueError('Original C counts or retained domain mismatch')
            added_by_stage={k:sum(o['stage_instance_id']==k and ident(o) not in oldset for o in new_rows) for k in warm}
            records.append({'case_id':case,'scene_id':sid,'S1_candidate_sha256':c['warm_candidate_sha256'],
                'old_opened':old,**record,'old_options':len(old_rows),'new_options':len(new_rows),
                'new_stage_options_added':added_by_stage,'old_options_retained':True,
                'new_option_labels_sha256':canonical(sorted(newset)),
                'proof_scope':'necessary individual labels only; not complete feasibility or thermal safety; no U',
                'hypothetical_mask_not_production_condition':True})
    READS[Path(__file__).relative_to(ROOT).as_posix()]=digest(Path(__file__).read_bytes())
    after={p:digest((ROOT/p).read_bytes()) for p in READS}
    if READS!=after:raise ValueError('Input/source drift')
    facts={'rule':RULE,'records':records,'source_sha256':READS,'read_after_sha256':after,'source_unchanged':True,
        'guard':GUARD,'research_calls':0,'models':0,'thermal_calls':0,'full_candidate_evaluations':0,
        'new_U':False,'elapsed_s':time.perf_counter()-t}
    out.mkdir(parents=True)
    (out/'facts.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps({'rows':len(records),'selected':[(x['case_id'],x['scene_id'],x['selected']) for x in records],
        'options':[(x['old_options'],x['new_options']) for x in records],'research_calls':0,'guard':GUARD},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    sys.addaudithook(audit);sys.setprofile(profile)
    try:run(p.parse_args().out)
    finally:sys.setprofile(None)
