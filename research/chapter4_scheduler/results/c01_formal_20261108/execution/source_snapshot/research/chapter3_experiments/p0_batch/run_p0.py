"""K154 P0 preparation and stored-record admission, not a run authorization.

Only pure input expansion, mock prechecks and preparation are exposed by CLI.
The unchanged method dispatcher is usable by a later separately frozen launcher.
"""
import argparse
import ast
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import platform
import shutil
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT))
from run_four_method_comparison import canonical, read, save, sha, now

PROTOCOL = 'K154-P0-base-R1-R5-preparation-v1'
PROBLEMS = tuple('base__R'+str(n) for n in range(1, 6))
PLAN = ROOT/'plans/k153_execution_plan_v1.json'
BASE = ROOT/'results/four_method_comparison01/declaration.json'
PREP = ROOT/'results/p0_batch_preparation01'
SECONDS = 300
METHODS = (
    {'id':'whole_milp', 'method':'milp'},
    {'id':'anchor_linked4', 'method':'linked_fixed_unit_opp_start',
     'opened_count':4, 'preeliminate_closed_anchors':True},
    {'id':'heft', 'method':'heft', 'seed':None})
NORMAL = frozenset(('NORMAL_COMPLETION','NORMAL_TIME_LIMIT',
                    'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST'))


def jobs(problem_id):
    if problem_id not in PROBLEMS:
        raise ValueError('P0 permits base__R1..R5 only')
    blocks = [[deepcopy(j)] for j in METHODS] + [[
        {'id':'sa'+str(seed),'method':'sa','seed':seed} for seed in range(101,106)]]
    k = PROBLEMS.index(problem_id) % 4
    blocks = blocks[k:]+blocks[:k]
    return [j for block in blocks for j in block]


def slots():
    return [dict(job, problem_id=p, slot_id=p+'__'+job['id'],
                 seconds=SECONDS, ordinal=i*8+n+1)
            for i,p in enumerate(PROBLEMS) for n,job in enumerate(jobs(p))]


def fresh_input(problem_id, budget=None):
    if problem_id not in PROBLEMS:
        raise ValueError('Undeclared problem')
    from inputs import build_instance, load_config
    from control_policy import with_auto_low_idle, resolve_idle_policy
    from run_neighborhood_diagnostic import opened_stages
    from run_four_method_comparison import masks
    raw = load_config()
    instance = build_instance(raw,problem_id,budget=budget)
    config,instance = with_auto_low_idle(raw),with_auto_low_idle(instance)
    if (instance['id']!=problem_id or F(instance['window_ms'])!=400
        or F(instance['start_grid_ms'])!=5
        or resolve_idle_policy(instance)!='auto_low_immediate_v1'
        or any(any(F(t)!=50 for t in s['entry']['temperature_degC'])
               or any(F(t)!=80 for t in s['maximum_temperature_degC'])
               for s in instance['scenarios'])):
        raise ValueError('Original P0 physical/time/control conditions changed')
    opened_stages(instance); masks(instance,4)
    return raw,config,instance


def input_declaration(problem_id):
    from run_four_method_comparison import scene_spec, masks
    from run_neighborhood_diagnostic import opened_stages
    raw,config,instance=fresh_input(problem_id)
    identities=dict(zip(('raw_config_sha256','config_sha256','input_sha256'),
                        map(canonical,(raw,config,instance))))
    return {'problem_id':problem_id,**identities,'input_identities':identities,
            'scene_spec':scene_spec(instance),
            'first_opened_by_scene':opened_stages(instance),
            'linked_opened_by_job':{'anchor_linked4':masks(instance,4)}},(raw,config,instance)


def sources():
    from run_four_method_comparison import sources as inherited
    current=inherited()
    if current!=read(BASE)['source_sha256'] or len(current)!=178:
        raise ValueError('K152 178 production/input files must remain unchanged')
    paths=list(HERE.glob('*.py'))+[HERE/'audit_lineage.json',HERE/'protocol.md',
        PLAN,ROOT/'plans/k153_plan_check.json',
        ROOT/'results/anchor_pair_preparation01/resume_unstarted.py']
    return {**current,**{p.relative_to(REPO).as_posix():sha(p) for p in sorted(paths)}}


def lineage_issues():
    issues=[]
    for item in read(HERE/'audit_lineage.json'):
        p=REPO/item['origin']
        original=p.read_text(encoding='utf-8')
        if sha(p)!=item['origin_sha256']:
            issues.append(item['file']+':ORIGIN_CHANGED')
        if not item.get('whole_file'):
            lines=original.splitlines(keepends=True)
            nodes={n.name:n for n in ast.parse(original).body if isinstance(n,ast.FunctionDef)}
            original='\n\n'.join(''.join(lines[nodes[name].lineno-1:nodes[name].end_lineno]).rstrip()
                                   for name in item['functions'])+'\n'
        for old,new in item['replacements']:
            if original.count(old)!=1:issues.append(item['file']+':REPLACEMENT_AMBIGUOUS')
            original=original.replace(old,new)
        expected=original if item.get('whole_file') else item['header']+'\n'+original
        if (HERE/item['file']).read_text(encoding='utf-8')!=expected:
            issues.append(item['file']+':UNDECLARED_CODE_CHANGE')
    return issues


def result_records(job,result,declaration,folder,**kw):
    if job not in jobs(declaration['problem_id']):
        raise ValueError('Unbound method identity')
    if job['method']=='milp':
        from audit_whole import result_records as audit
        return audit(result,declaration,folder,**kw)
    if job['method']=='linked_fixed_unit_opp_start':
        import audit_cutoff as adapter
        from execution_status import classify_execution
        record=adapter.correct_records(job,result,declaration,folder,**kw)
        if record.get('cutoff_audit',{}).get('applied'):
            _,python,_,_=adapter._last_mapping(result,folder)
            cancel=Path(folder)/'matlab'/f"request_{python['request_number']:06d}.cancel"
            valid=cancel.is_file() and cancel.read_text(encoding='ascii').strip()=='budget'
            record['cutoff_audit']['cancel_file_verified']=valid
            if not valid:
                record['context']['hard_errors'].append('MISSING_MATCHING_ROOT_CANCEL_FILE')
                record['execution']=classify_execution(result,record['context'])
        return record
    from audit_heuristic import result_records as audit
    return audit(result,declaration,**kw)


class MockLedger:
    """TEST_ONLY accounting; never creates a research claim or authorizes dispatch."""
    def __init__(self):
        self.consumed=[]
        self.blocked=False

    def consume(self, slot):
        if self.blocked or len(self.consumed)>=40 or slot!=slots()[len(self.consumed)]:
            raise ValueError('STOP, duplicate, reordered or exhausted slot')
        self.consumed.append(deepcopy(slot))

    def complete(self,status):
        if status not in NORMAL:self.blocked=True


def check_gate(path):
    g=read(path)
    if (g.get('protocol')!=PROTOCOL or g.get('passed') is not True
        or g.get('source_sha256')!=sources() or g.get('source_unchanged') is not True
        or not g.get('tests_run') or g.get('errors')!=0 or g.get('failures')!=0
        or g.get('skipped')!=0 or g.get('error') is not None
        or not g.get('blocked_calls') or any(g['blocked_calls'].values())
        or any(g.get(k)!=0 for k in ('research_calls','native_calls','physical_models','thermal_evaluations'))):
        raise ValueError('Matching, successful zero-research P0 precheck required')
    return g


def prepare(out,checks):
    out=Path(out).resolve()
    out.relative_to(REPO)
    check_gate(checks)
    if lineage_issues():raise ValueError('Audit/dispatcher lineage mismatch')
    before=sources()
    values={p:input_declaration(p) for p in PROBLEMS}
    if values['base__R1'][0]['input_identities']!=read(BASE)['input_identities']:
        raise ValueError('Original pilot input identity drift')
    out.mkdir(parents=True,exist_ok=False)
    inputs={}
    for pid,(d,triple) in values.items():
        folder=out/'inputs'/pid;folder.mkdir(parents=True)
        for name,value in zip(('raw','config','instance'),triple):save(folder/(name+'.json'),value)
        inputs[pid]=d
    for name,digest in before.items():
        dest=out/'source_snapshot'/name;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(REPO/name,dest)
        if sha(dest)!=digest:raise ValueError('Snapshot race')
    shutil.copyfile(checks,out/'precheck.json')
    d={'protocol':PROTOCOL,'state':'PREPARED_NOT_AUTHORIZED','authorised_to_execute':False,
       'prepared_at_utc':now(),'problem_ids':list(PROBLEMS),'inputs':inputs,'slots':slots(),
       'proposed_calls':40,'proposed_seconds_each':300,'proposed_method_budget_s':12000,
       'proposed_calendar_reserve_s':19200,'source_sha256':before,
       'precheck_sha256':sha(out/'precheck.json'),'plan_sha256':sha(PLAN),
       'research_calls':0,'real_batch_launcher':'NOT_ENABLED_PENDING_SEPARATE_BUDGET_AND_LAUNCH_FREEZE',
       'pilot_reuse':'K152 separate; P0 R1 explicit proposed replication; no free witnesses or cache',
       'environment':{'python':sys.version,'platform':platform.platform()}}
    save(out/'declaration.json',d)
    save(out/'ledger.json',{'protocol':PROTOCOL,'state':'NOT_AUTHORIZED','consumed':0,
                           'reserved_method_budget_s':0,'calls':[]})
    save(out/'authorization.example.json',{'approved':False,'declaration_sha256':sha(out/'declaration.json'),
        'note':'Example only; not a machine-approved research budget or execution chain'})
    if sources()!=before:raise ValueError('Sources changed during preparation')
    return admission(out)


def admission(out):
    out=Path(out).resolve();out.relative_to(REPO)
    d=read(out/'declaration.json')
    if (d.get('protocol')!=PROTOCOL or d.get('slots')!=slots()
        or d.get('source_sha256')!=sources() or d.get('authorised_to_execute') is not False
        or d.get('plan_sha256')!=sha(PLAN) or d.get('proposed_calls')!=40
        or d.get('proposed_seconds_each')!=300 or d.get('proposed_method_budget_s')!=12000
        or set(d.get('inputs',{}))!=set(PROBLEMS)
        or d.get('precheck_sha256')!=sha(out/'precheck.json')):
        raise ValueError('P0 preparation/source/protocol binding mismatch')
    check_gate(out/'precheck.json')
    for pid in PROBLEMS:
        triples=[read(out/'inputs'/pid/(n+'.json')) for n in ('raw','config','instance')]
        fresh,triple=input_declaration(pid)
        if triples!=list(triple) or d['inputs'][pid]!=fresh:
            raise ValueError('Problem-specific input mismatch: '+pid)
    for name,h in d['source_sha256'].items():
        if sha(out/'source_snapshot'/name)!=h:raise ValueError('Source snapshot mismatch')
    ledger=read(out/'ledger.json')
    if ledger!={'protocol':PROTOCOL,'state':'NOT_AUTHORIZED','consumed':0,
                'reserved_method_budget_s':0,'calls':[]}:
        raise ValueError('Preparation ledger unexpectedly consumed')
    return {'prepared':True,'authorised_to_execute':False,'slots':40,'research_calls':0,
            'source_files':len(d['source_sha256']),'problem_inputs':5}


def precheck(out):
    import precheck_p0
    return precheck_p0.run(out)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('precheck','prepare','inspect','run'))
    p.add_argument('--out',type=Path,default=PREP)
    p.add_argument('--checks',type=Path)
    a=p.parse_args()
    if a.mode=='run':p.error('K154 exposes no real launcher; obtain a separate concrete budget and launch freeze')
    elif a.mode=='precheck':raise SystemExit(0 if precheck(a.out) else 1)
    elif a.mode=='prepare':
        if a.checks is None:p.error('prepare requires --checks')
        print(json.dumps(prepare(a.out,a.checks)))
    else:print(json.dumps(admission(a.out)))
