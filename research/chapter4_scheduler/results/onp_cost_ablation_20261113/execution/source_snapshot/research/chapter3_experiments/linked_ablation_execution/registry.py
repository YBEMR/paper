"""K173 narrow once-only batch contract; standard-library metadata only."""
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
OUT=SCIENCE/'results/linked_ablation_execution01'
GLOBAL_CLAIM=SCIENCE/'results/linked_ablation_execution_claim01.json'
PROTOCOL='K173-linked-ablation-execution-v1'
ORDER=[('base__R1','A'),('base__R1','B'),('base__R1','C'),
       ('base__R3','C'),('base__R3','B'),('base__R3','A')]
BUDGETS={'method_s':300,'method_total_s':1800,'post_s':60,'post_total_s':360,
         'calendar_s':3600,'method_return_s':420,'slot_s':480}


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text('utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,
        separators=(',',':'),allow_nan=False).encode()).hexdigest()


def write_new(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')


def save(path,value):
    """Single writer atomic replace; bounded IO retry, never research retry."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    pending=path.with_name(path.name+'.'+uuid.uuid4().hex+'.pending')
    write_new(pending,value)
    end=time.monotonic()+1
    while True:
        try:os.replace(pending,path);return
        except PermissionError:
            if time.monotonic()>=end:raise
            time.sleep(.02)


def output_path(declaration):
    value=(REPO/declaration['output_directory']).resolve()
    if value!=OUT.resolve():raise ValueError('Only the new K173 output is allowed')
    return value


def slot_spec(declaration,slot_id):
    values=[s for s in declaration['slots'] if s['slot_id']==slot_id]
    if len(values)!=1:raise ValueError('Unknown or repeated K173 slot')
    return values[0]


def case_spec(declaration,case_id):
    values=[c for c in declaration['cases'] if c['common']['case_id']==case_id]
    if len(values)!=1:raise ValueError('Unknown K173 case')
    return values[0]


def validate_declaration(declaration,*,check_sources=True):
    d=declaration
    if (d.get('protocol')!=PROTOCOL or d.get('authorized') is not True
            or d.get('scientific_execution_enabled') is not True
            or d.get('authorization_origin')!='direct human K173 message, six K172 calls only'
            or d.get('budgets')!=BUDGETS):raise ValueError('Invalid K173 authority/budget contract')
    output_path(d)
    if [(s['case_id'],s['variant']) for s in d['slots']]!=ORDER:
        raise ValueError('Six-slot order drift')
    if len({s['slot_id'] for s in d['slots']})!=6 or any(
        s['slot_id']!=s['case_id']+'__'+s['variant'] or s['method_seconds']!=300
        or s['post_seconds_max']!=60 or s['ordinal']!=i+1
        for i,s in enumerate(d['slots'])):raise ValueError('Slot identity/budget drift')
    for case_id in ('base__R1','base__R3'):
        c=case_spec(d,case_id);common=c['common'];r=c['recipes']
        for arm in ('A','B','C'):
            k=r[arm]['kwargs']
            if (k['seconds']!=300 or k['scene_slice_s']!=(150 if arm=='A' else 60)
                    or k['shared_deployment']!=common['shared_deployment']
                    or k['builder_options']!=common['builder_options']
                    or k['opened_by_scene']!=common['first_opened_by_scene']):
                raise ValueError('Common search recipe drift')
            if arm=='A':
                if (r[arm]['entry_module']!='neighborhood_method'
                    or r[arm]['entry_function']!='execute_n1_neighborhood'
                    or set(k)!={'seconds','scene_slice_s','shared_deployment','builder_options','opened_by_scene'}):
                    raise ValueError('A must be original N1 with no second pass')
            elif (r[arm]['entry_module']!='linked_method'
                  or r[arm]['entry_function']!='execute_linked_fixed_unit_opp_start'
                  or k['linked_opened_by_scene']!=common['second_opened_by_scene']
                  or k['preeliminate_closed_anchors'] is not (arm=='C')
                  or set(k)!={'seconds','scene_slice_s','shared_deployment','builder_options','opened_by_scene',
                              'linked_opened_by_scene','preeliminate_closed_anchors'}):
                raise ValueError('B/C must differ only in phase-2 anchor toggle')
            if r[arm]['new_bound_filter'] is not False:raise ValueError('K170 search filter forbidden')
    if check_sources:
        proposal_path=SCIENCE/'results/linked_ablation_preparation01/preparation02/proposal.json'
        proposal=read(proposal_path)
        normalized=json.loads(json.dumps(d['cases']))
        for c in normalized:
            for r in c['recipes'].values():r['scientific_execution_authorized']=False
        if (normalized!=proposal['cases'] or d['solver_options']!=proposal['solver_options']
                or d['scientific_source_sha256']!=proposal['source_sha256']
                or d['proposal_sha256']!=sha(proposal_path)
                or d['clock_start_policy']!=proposal['clock_start_policy']):
            raise ValueError('K172 frozen model/initialization/options/import policy drift')
        for name,digest in d['source_sha256'].items():
            p=(REPO/name).resolve();p.relative_to(REPO)
            if not p.is_file() or sha(p)!=digest:raise ValueError('Frozen source drift: '+name)
        for name,digest in d['frozen_dependency_sha256'].items():
            if sha(REPO/name)!=digest:raise ValueError('Frozen protocol/check drift: '+name)
    return d


def load_declaration(path,repo=None):
    path=Path(path).resolve()
    if path!=OUT.resolve()/'declaration.json':raise ValueError('Unexpected declaration location')
    d=validate_declaration(read(path))
    frozen=read(path.parent/'declaration_binding.json')
    if frozen['declaration_sha256']!=sha(path):raise ValueError('Declaration changed after freezing')
    if Path(sys.executable).resolve()!=Path(d['environment']['python_executable']).resolve():
        raise ValueError('Python executable changed')
    return d
