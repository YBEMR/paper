"""K176 exact two-call authority and frozen identities; standard library only."""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid

SCIENCE=Path(__file__).resolve().parent.parent
REPO=SCIENCE.parents[1]
OUT=SCIENCE/'results/linked_release_execution01'
GLOBAL_CLAIM=SCIENCE/'results/linked_release_execution_claim01.json'
PROTOCOL='K176-C-vs-conditional-release-execution-v1'
ORDER=[('base__R3','C'),('base__R3','conditional_release')]
BUDGETS={'method_s':300,'method_total_s':600,'post_s':60,'post_total_s':120,
    'calendar_s':1200,'method_return_s':420,'slot_s':480}
PROPOSAL=SCIENCE/'results/linked_release_integration01/next_proposal.json'

def now():return datetime.now(timezone.utc).isoformat()
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def canonical(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def write_new(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8') as f:json.dump(v,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
def save(p,v):
    p=Path(p);pending=p.with_name(p.name+'.'+uuid.uuid4().hex+'.pending');write_new(pending,v)
    end=time.monotonic()+1
    while True:
        try:os.replace(pending,p);return
        except PermissionError:
            if time.monotonic()>=end:raise
            time.sleep(.02)
def slot_spec(d,slot_id):
    rows=[s for s in d['slots'] if s['slot_id']==slot_id]
    if len(rows)!=1:raise ValueError('Unknown/repeated slot')
    return rows[0]
def case_spec(d,case_id):
    rows=[c for c in d['cases'] if c['common']['case_id']==case_id]
    if len(rows)!=1:raise ValueError('Unknown case')
    return rows[0]
def output_path(d):
    p=(REPO/d['output_directory']).resolve()
    if p!=OUT.resolve():raise ValueError('Only new K176 output permitted')
    return p
def validate_declaration(d,*,check_sources=True):
    if (d.get('protocol')!=PROTOCOL or d.get('authorized') is not True
        or d.get('scientific_execution_enabled') is not True
        or d.get('authorization_origin')!='direct human K176 message, two K175 R3 calls only'
        or d.get('budgets')!=BUDGETS or d.get('no_retry') is not True):raise ValueError('K176 authority/budget')
    output_path(d)
    if [(s['case_id'],s['variant']) for s in d['slots']]!=ORDER:raise ValueError('Order/count drift')
    for n,s in enumerate(d['slots'],1):
        if s['slot_id']!=s['case_id']+'__'+s['variant'] or s['ordinal']!=n or s['method_seconds']!=300 or s['post_seconds_max']!=60:raise ValueError('Slot identity')
    if len(d['cases'])!=1 or d['cases'][0]['common']['case_id']!='base__R3':raise ValueError('Only P0 R3')
    c=d['cases'][0]
    if set(c['recipes'])!={'C','conditional_release'}:raise ValueError('Only two versions')
    for variant,module,function in [('C','linked_method','execute_linked_fixed_unit_opp_start'),('conditional_release','linked_release_method','execute_linked_conditional_release')]:
        r=c['recipes'][variant];k=r['kwargs']
        if r['entry_module']!=module or r['entry_function']!=function or r['variant']!=variant or k['seconds']!=300 or k['scene_slice_s']!=60 or r['new_bound_filter'] is not False:raise ValueError('Recipe drift')
    if c['recipes']['C']['kwargs']['preeliminate_closed_anchors'] is not True or 'preeliminate_closed_anchors' in c['recipes']['conditional_release']['kwargs']:raise ValueError('Frozen C presolve/new implicit presolve')
    if d.get('K168_authorized_here') is not False or d.get('deadline_remainder_authorized_here') is not False:raise ValueError('Suspended tasks forbidden')
    if check_sources:
        p=read(PROPOSAL);expected={'common':p['common'],'recipes':deepcopy(p['recipes'])}
        for r in expected['recipes'].values():r['scientific_execution_authorized']=True
        if d['cases']!=[expected] or d['solver_options']!=p['solver_options'] or d['clock_start_policy']!=p['clock_start_policy'] or d['proposal_sha256']!=sha(PROPOSAL) or d['scientific_source_sha256']!=p['source_sha256']:raise ValueError('K175 approved scientific identity drift')
        for field in ('source_sha256','frozen_dependency_sha256','protected_archive_sha256'):
            for name,digest in d[field].items():
                path=(REPO/name).resolve();path.relative_to(REPO)
                if not path.is_file() or sha(path)!=digest:raise ValueError('Frozen source/archive drift: '+name)
    return d
def load_declaration(path,repo=None):
    path=Path(path).resolve()
    if path!=OUT.resolve()/'declaration.json':raise ValueError('Wrong declaration path')
    d=validate_declaration(read(path));binding=read(path.parent/'declaration_binding.json')
    if binding['declaration_sha256']!=sha(path):raise ValueError('Frozen declaration changed')
    if Path(sys.executable).resolve()!=Path(d['environment']['python_executable']).resolve():raise ValueError('Wrong Python')
    return d
