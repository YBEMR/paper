"""Versioned file identities and a disabled-by-default human authorization gate."""
import hashlib,json,os
from pathlib import Path
from h02_pair_preflight.common import BASE_SHA,require,encoded,sha
HERE=Path(__file__).resolve().parent
CORE=HERE.parent
SCIENTIFIC_POLICY_SHA256='916b07173b9ed7923f0cc37859828fa31e3cb60b51ad9fff67d05af1c6a2f18f'

def load_json(path):
    def unique(pairs):
        out={}
        for k,v in pairs: require(k not in out,'DUPLICATE_JSON_KEY'); out[k]=v
        return out
    def nonfinite(v): raise ValueError('NONFINITE_JSON:'+v)
    return json.loads(Path(path).read_bytes().decode('utf-8'),object_pairs_hook=unique,parse_constant=nonfinite)

def atomic_json(path,value):
    path=Path(path); tmp=path.with_name(path.name+'.tmp')
    with tmp.open('xb') as f: f.write(encoded(value)); f.flush(); os.fsync(f.fileno())
    os.replace(tmp,path)

def digest_file(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def require_research_authorization(gate,policy):
    require(gate.get('research_authorized') is True and gate.get('four_slot_authorized') is True and policy.get('execution_enabled') is True,'B0_RESEARCH_EXECUTION_NOT_AUTHORIZED')
    require(isinstance(gate.get('approval_reference'),str) and gate['approval_reference'].strip(),'MISSING_EXPLICIT_USER_AUTHORIZATION_REFERENCE')
    require(sha({k:v for k,v in policy.items() if k!='execution_enabled'})==SCIENTIFIC_POLICY_SHA256,'H02_SCIENTIFIC_SCOPE_DRIFT')
    identifier=gate.get('authorization_id')
    require(isinstance(identifier,str) and identifier and identifier.replace('-','').replace('_','').isalnum(),'MISSING_UNIQUE_AUTHORIZATION_ID')
    require(all(isinstance(gate.get(k),str) and Path(gate[k]).is_absolute() for k in ('allowed_run_directory','authority_store')),'MISSING_FROZEN_RUN_OR_AUTHORITY_STORE')
    require(policy['base_sha']==BASE_SHA and policy['plan_limit_s']==120 and policy['audit_limit_s']==60,'AUTHORIZATION_SCOPE_DRIFT')
    return True

def policy_files(): return load_json(HERE/'policy.json'),load_json(HERE/'execution_gate.json')


def consume_worker_launch(job,gate,policy,output):
    """Internal worker CLI is not a second route around controller once-claims."""
    require_research_authorization(gate,policy)
    ordinal=job.get('ordinal'); require(type(ordinal) is int and 1<=ordinal<=4,'WORKER_SLOT_ORDINAL')
    slot=policy['slots'][ordinal-1]; kind=job['kind']; require(kind in ('planner','audit'),'WORKER_KIND')
    run=Path(gate['allowed_run_directory']).resolve(); store=Path(gate['authority_store'])
    global_claim=load_json(store/(gate['authorization_id']+'.claim.json'))
    require(global_claim.get('authorization_id')==gate['authorization_id'] and global_claim.get('gate_sha256')==sha(gate) and Path(global_claim['run_directory']).resolve()==run,'WHOLE_RUN_AUTHORIZATION_CLAIM')
    claim_name=('slot_' if kind=='planner' else 'audit_')+str(ordinal)
    claim=load_json(run/'ledger'/(claim_name+'.claim.json'))
    require(sha(claim)==job['launch_claim_sha256'] and claim['root_origin']==job['root_origin'] and claim['budget_s']==job['limit_s'],'WORKER_LAUNCH_CLAIM_IDENTITY')
    expected=run/('slot_'+str(ordinal))/('planner_public' if kind=='planner' else 'H_audit_private')
    require(Path(output).resolve()==expected.resolve(),'WORKER_OUTPUT_DIRECTORY_IDENTITY')
    if kind=='planner':
        require(job['packet']['problem_id']==slot['problem_id'] and job['packet']['view']==slot['view'] and claim['slot']==slot,'WORKER_PLANNER_SLOT_IDENTITY')
    else:
        require(job['token']['problem_id']==slot['problem_id'] and job['token']['view']==slot['view'] and claim['token_sha256']==sha(job['token']) and job['audit_claim_sha256']==sha(claim),'WORKER_AUDIT_TOKEN_IDENTITY')
    target=store/(gate['authorization_id']+'_'+str(ordinal)+'_'+kind+'.worker.claim.json')
    with target.open('xb') as f: f.write(encoded({'launch_claim_sha256':sha(claim),'job_sha256':sha(job),'consumed_before_core_entry':True})); f.flush(); os.fsync(f.fileno())
    return str(target)
