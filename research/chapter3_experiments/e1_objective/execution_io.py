"""Frozen identities and explicitly selected E1/E2/E3/E4 protocols; no science imports."""
import hashlib
import json
import os
from pathlib import Path
import uuid

CORE=Path(__file__).resolve().parents[1]
REPO=CORE.parents[1]
DEFAULT_GATE=Path(__file__).with_name('execution_gate.json')
BUDGETS=dict(plan_s=300,post_s=60,plan_calls=4,post_calls=4)
_E1_SLOTS=(('base__R1','FULL'),('base__R1','OMIT_TEMP'),('base__R3','OMIT_TEMP'),('base__R3','FULL'))
SLOTS=[list(slot) for slot in _E1_SLOTS]
CORE_FILES=['heft_method.py','schedules.py','start_domain.py','auto_heuristic_policy.py',
            'control_policy.py','thermal.py','timing.py','inputs.py',
            'h02_pair_preflight/__init__.py','h02_pair_preflight/common.py','h02_pair_preflight/receipts.py',
            'h02_pair_b0/__init__.py','h02_pair_b0/budget.py','h02_pair_b0/boundary.py']
E1_FILES=['__init__.py','search.py','scoring.py','runner.py','exports.py','boundary.py',
          'ledger.py','process_control.py','execution_io.py','worker.py','controller.py']


def require(value,reason):
    if not value: raise ValueError(reason)


def packed(value): return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def sha(value): return hashlib.sha256(packed(value)).hexdigest()
def file_sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    def unique(pairs):
        out={}
        for k,v in pairs:
            require(k not in out,'DUPLICATE_JSON_KEY'); out[k]=v
        return out
    def invalid(value): raise ValueError('NONFINITE_JSON:'+value)
    return json.loads(Path(path).read_bytes().decode('utf-8'),object_pairs_hook=unique,parse_constant=invalid)


def save(path,value):
    path=Path(path); temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    with temp.open('xb') as f:
        f.write(packed(value)+b'\n'); f.flush(); os.fsync(f.fileno())
    os.replace(temp,path)


def protocol_slots(manifest):
    # Missing ID is permitted only for historical E1 manifests. An explicit
    # unknown or mixed protocol must never silently fall back to E1.
    protocol=manifest.get('protocol_id','E1_OBJECTIVE_V1')
    if protocol=='E1_OBJECTIVE_V1': slots=_E1_SLOTS
    elif protocol=='E2_RESOURCES_V1':
        from e2_resources.protocol import SLOTS as slots
    elif protocol=='E3_DEPLOYMENT_V1':
        from e3_deployment.protocol import SLOTS as slots
    elif protocol=='E4_DEADLINE_V1':
        from e4_deadline.protocol import SLOTS as slots
    else: raise ValueError('UNKNOWN_EXECUTION_PROTOCOL')
    return [list(slot) for slot in slots]


def protocol_limits(scope):
    protocol=scope.get('protocol_id','E1_OBJECTIVE_V1')
    if protocol in ('E1_OBJECTIVE_V1','E2_RESOURCES_V1'):
        return dict(budgets=dict(plan_s=300,post_s=60,plan_calls=4,post_calls=4),
                    supervision=dict(slot_wall_s=420,batch_wall_s=1800,archive_only_grace_s=5))
    if protocol=='E3_DEPLOYMENT_V1':
        from e3_deployment.protocol import BUDGETS as budgets,SUPERVISION
        return dict(budgets=dict(budgets),supervision=dict(SUPERVISION))
    if protocol=='E4_DEADLINE_V1':
        from e4_deadline.protocol import BUDGETS as budgets,SUPERVISION
        return dict(budgets=dict(budgets),supervision=dict(SUPERVISION))
    raise ValueError('UNKNOWN_EXECUTION_PROTOCOL')


def runtime_paths(mode):
    require(mode in ('MOCK_PROCESS','REAL_RESEARCH'),'EXECUTION_MODE')
    relative=['research/chapter3_experiments/'+x for x in CORE_FILES]
    relative+=['research/chapter3_experiments/e1_objective/'+x for x in E1_FILES]
    relative+=['research/v1_evaluator/interval.py',
               'research/chapter3_experiments/e2_resources/__init__.py',
               'research/chapter3_experiments/e2_resources/protocol.py',
               'research/chapter3_experiments/e3_deployment/__init__.py',
               'research/chapter3_experiments/e3_deployment/protocol.py',
               'research/chapter3_experiments/e3_deployment/input_contract.py',
               'research/chapter3_experiments/e4_deadline/__init__.py',
               'research/chapter3_experiments/e4_deadline/protocol.py']
    if mode=='MOCK_PROCESS': relative+=['research/chapter3_experiments/e1_objective/mock_fixtures.py']
    return relative


def validate_gate(gate,manifest,mode,run_dir):
    require(mode in ('MOCK_PROCESS','REAL_RESEARCH'),'EXECUTION_MODE')
    require(gate.get('kind')==mode,'AUTHORIZATION_KIND_MISMATCH')
    if mode=='REAL_RESEARCH':
        approved=gate.get('stage_authorized') if manifest.get('protocol_id') in ('E3_DEPLOYMENT_V1','E4_DEADLINE_V1') else gate.get('four_slot_authorized')
        require(gate.get('authorized') is True and approved is True and
                isinstance(gate.get('approval_reference'),str) and gate['approval_reference'].strip(),
                'E1_REAL_RESEARCH_NOT_AUTHORIZED')
    else: require(gate.get('mock_only') is True and gate.get('authorized') is not True,'MOCK_GATE')
    require(manifest.get('mode')==mode,'MANIFEST_MODE')
    require(gate.get('source_sha')==manifest.get('source_sha') and
            gate.get('scope_sha256')==sha(manifest),'SOURCE_OR_SCOPE_DRIFT')
    limits=protocol_limits(manifest)
    protocol=manifest.get('protocol_id','E1_OBJECTIVE_V1')
    if 'protocol_id' in gate or protocol in ('E3_DEPLOYMENT_V1','E4_DEADLINE_V1'):
        require(gate.get('protocol_id')==protocol,'AUTHORIZATION_PROTOCOL_MISMATCH')
    require(gate.get('budgets')==limits['budgets'] and manifest.get('budgets')==limits['budgets'] and
            manifest.get('slots')==protocol_slots(manifest),'BUDGET_OR_SLOTS_DRIFT')
    if 'supervision' in manifest or protocol in ('E3_DEPLOYMENT_V1','E4_DEADLINE_V1'):
        require(manifest.get('supervision')==limits['supervision'],'SUPERVISION_DRIFT')
    require(isinstance(gate.get('authorization_id'),str) and gate['authorization_id'],'AUTHORIZATION_ID')
    for key in ('authority_store','allowed_run_directory'):
        require(isinstance(gate.get(key),str) and Path(gate[key]).is_absolute(),'FIXED_ABSOLUTE_'+key)
    require(Path(run_dir).resolve()==Path(gate['allowed_run_directory']).resolve(),'RUN_DIRECTORY_DRIFT')
    # Authority storage cannot move when changing result directories.
    require(not Path(gate['authority_store']).resolve().is_relative_to(Path(run_dir).resolve()),'AUTHORITY_STORE_INSIDE_RUN')
    return gate


def build_bundle(destination,manifest,mode,*,repo=REPO):
    dest=Path(destination); require(not dest.exists(),'BUNDLE_REUSED')
    expected=set(runtime_paths(mode))
    require(set(manifest['files'])==expected,'RUNTIME_ALLOWLIST_DRIFT')
    dest.mkdir(parents=True)
    for rel,digest in manifest['files'].items():
        require(file_sha(Path(repo)/rel)==digest,'SOURCE_DRIFT:'+rel)
        target=dest/rel; target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((Path(repo)/rel).read_bytes())
    save(dest/'runtime_manifest.json',manifest)
    return dest/'research/chapter3_experiments/e1_objective/worker.py'


def verify_bundle(bundle,manifest):
    require(set(manifest['files'])==set(runtime_paths(manifest['mode'])),'BUNDLE_ALLOWLIST')
    for rel,digest in manifest['files'].items(): require(file_sha(Path(bundle)/rel)==digest,'BUNDLE_HASH:'+rel)


def verify_job(job,gate,manifest,output):
    mode=job['mode']; validate_gate(gate,manifest,mode,job['run_dir'])
    require(job['scope_sha256']==sha(manifest),'JOB_MANIFEST')
    require(job['phase'] in ('PLAN','POST') and type(job['ordinal']) is int and 1<=job['ordinal']<=len(protocol_slots(manifest)),'JOB_SLOT')
    require(job['limit_s']==protocol_limits(manifest)['budgets'][job['phase'].lower()+'_s'],'JOB_FIXED_ROOT_LIMIT')
    claim=job['claim']
    require(all(claim.get(k)==job[k] for k in ('phase','ordinal','root_origin','limit_s')),'CLAIM_JOB_TIMING_OR_SLOT')
    require(claim.get('source_sha')==manifest['source_sha'] and claim.get('kind')==mode and
            Path(claim['run_dir']).resolve()==Path(job['run_dir']).resolve(),'CLAIM_JOB_SOURCE_OR_RUN')
    require(Path(output).resolve()==Path(job['run_dir']).resolve()/('slot_'+str(job['ordinal']))/job['phase'].lower(),
            'WORKER_OUTPUT_IDENTITY')
    packet=job['packet']; i,c=packet['instance'],packet['config']
    require(set(packet)=={'instance','config','objective'},'PACKET_FIELDS')
    if mode=='REAL_RESEARCH':
        require(job.get('mock_behavior') is None and job.get('mock_prior_elapsed_s',0)==0,'MOCK_CONTROL_IN_REAL_JOB')
        problem,objective=protocol_slots(manifest)[job['ordinal']-1]
        require(i['id']==problem and packet['objective']==objective,'REAL_SLOT_IDENTITY')
        expected=manifest['inputs'][problem]
        require(sha(i)==expected['input_sha256'] and sha(c)==expected['config_sha256'],'FROZEN_INPUT_DRIFT')
    else: require(i['id'].startswith('MOCK_ONLY_'),'MOCK_RESEARCH_INPUT_FORBIDDEN')
    if job['phase']=='PLAN':
        ctx=claim['job_context']
        require(ctx['input_sha256']==sha(i) and ctx['config_sha256']==sha(c) and
                ctx['accuracy_sha256']==sha(c['accuracy_targets']) and ctx['objective']==packet['objective'] and
                ctx['packet_sha256']==sha(packet),'PLAN_CONTEXT_IDENTITY')
    else:
        require(sha(job['selected_token'])==claim['job_context']['selected_token_sha256'] and
                job['selected_token']==claim['job_context']['selected_token'],'POST_TOKEN_IDENTITY')
        token=job['selected_token']; result=job['planning_result']
        require(token==selected_token(packet,result) and sha(result)==claim['job_context']['plan_result_sha256'],
                'POST_NOT_FROZEN_SELECTED_PLAN')
    return True


def selected_token(packet,result):
    require(result.get('state')=='SAFE' and result.get('safe_candidate') is not None,'NO_SELECTED_SAFE')
    require(result.get('input_sha256')==sha(packet['instance']) and result.get('config_sha256')==sha(packet['config']) and
            result.get('objective')==packet['objective'],'TOKEN_PLAN_CONTEXT')
    return dict(input_sha256=sha(packet['instance']),config_sha256=sha(packet['config']),
                accuracy_sha256=sha(packet['config']['accuracy_targets']),objective=packet['objective'],
                planning_score_sha256=sha(result['planning_score_J']),receipt_sha256=sha(result['evaluation']),
                candidate_sha256=sha(result['safe_candidate']))
