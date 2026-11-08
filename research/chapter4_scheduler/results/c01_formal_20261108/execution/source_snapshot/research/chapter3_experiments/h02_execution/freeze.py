"""Bind direct K177 authorization; no scientific computation or process launch."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
CORE = HERE.parent
REPO = CORE.parent.parent
PRE = CORE/'results/response_information_execution_precheck01'
OUT = CORE/'results/response_information_execution01'
sys.path.insert(0, str(CORE))
from h02_pair_b0.bundle import runtime_sources, verify_runtime_freeze
from h02_pair_b0.io_contract import load_json, require_research_authorization, SCIENTIFIC_POLICY_SHA256
from h02_pair_preflight.common import sha

def file_sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def write_new(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('xb') as f:
        f.write((json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode('utf-8'))

def freeze(gates):
    gates = [Path(p).resolve() for p in gates]
    declaration = PRE/'execution_declaration.json'
    if declaration.exists() or OUT.exists() or (CORE/'results/response_information_execution_claim01.json').exists():
        raise FileExistsError('K177 already frozen or consumed; no replacement')
    for p in gates:
        g = load_json(p)
        if g.get('passed') is not True:
            raise ValueError('Passing precheck required: '+str(p))
    original = verify_runtime_freeze()
    b0 = CORE/'h02_pair_b0'
    original_policy = load_json(b0/'policy.json')
    original_gate = load_json(b0/'execution_gate.json')
    if original_policy['execution_enabled'] or original_gate['research_authorized']:
        raise ValueError('Expected unconsumed inherited disabled gate')
    # Preserve old authority/freeze bytes before the explicitly authorized rebinding.
    saved = PRE/'inherited_identity'
    saved.mkdir(exist_ok=False)
    for name in ('policy.json', 'execution_gate.json', 'evidence/runtime_freeze.json'):
        target = saved/name.replace('/', '_')
        with target.open('xb') as f:
            f.write((b0/name).read_bytes())
    policy = dict(original_policy, execution_enabled=True)
    gate = dict(original_gate, stage='K177_DIRECT_USER_FOUR_SLOT_EXECUTION',
        research_authorized=True, four_slot_authorized=True,
        approval_reference='Direct user message 2026-10-23: P0 R1/R2 H02 four HEFT plans 120s and unique H post 60s; stop after batch',
        authorization_note='This authorization applies only to this new four-slot batch; original B0 history remains disabled at f68787e.',
        authorization_id='H02_K177_R1R2_20261023_01',
        allowed_run_directory=str(OUT),
        authority_store=str(CORE/'results/response_information_execution_authority01'))
    require_research_authorization(gate, policy)
    for name, value in [('policy.json',policy), ('execution_gate.json',gate)]:
        (b0/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    current = {rel:file_sha(path) for rel,path in runtime_sources().items()}
    if current != original['source_files_sha256']:
        raise ValueError('Scientific/adapter source drift')
    runtime = dict(original,
        policy_files_sha256={name:file_sha(b0/name) for name in ('policy.json','execution_gate.json')},
        K177_authorization_rebind_only=True,
        inherited_runtime_freeze_sha256=file_sha(saved/'evidence_runtime_freeze.json'))
    (b0/'evidence/runtime_freeze.json').write_text(json.dumps(runtime,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    verify_runtime_freeze()
    paths = dict(runtime_sources())
    for name in ('policy.json','execution_gate.json','evidence/runtime_freeze.json'):
        paths[(b0/name).relative_to(REPO).as_posix()] = b0/name
    for p in HERE.glob('*'):
        if p.is_file() and p.suffix in ('.py','.md'):
            paths[p.relative_to(REPO).as_posix()] = p
    paths[(CORE/'config_v01.json').relative_to(REPO).as_posix()] = CORE/'config_v01.json'
    # Source verification reads this identity file before each input expansion.
    source_manifest=CORE/'h02_pair_preflight/evidence/source_manifest.json'
    paths[source_manifest.relative_to(REPO).as_posix()] = source_manifest
    expected = {rel:file_sha(p) for rel,p in paths.items()}
    decl = {
        'protocol':'H02-main-four-slot-execution-v1',
        'main_baseline_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        'source_H02_commit':subprocess.check_output(['git','rev-parse','f68787e'],cwd=REPO,text=True).strip(),
        'authorization_origin':gate['approval_reference'],
        'authorization_id':gate['authorization_id'],
        'frozen_utc':datetime.now(timezone.utc).isoformat(),
        'output_directory':str(OUT),
        'global_claim':str(CORE/'results/response_information_execution_claim01.json'),
        'calendar_limit_s':1200,
        'budgets':{'plan_s':120,'audit_s':60,'maximum_plan_calls':4,'maximum_audit_calls':4,
                   'plan_total_s':480,'audit_total_s':240,'scientific_total_s':720},
        'slots':policy['slots'],
        'policy_path':str(b0/'policy.json'),
        'gate_path':str(b0/'execution_gate.json'),
        'scientific_policy_sha256':SCIENTIFIC_POLICY_SHA256,
        'expected_sha':expected,
        'passing_prechecks':{Path(p).relative_to(REPO).as_posix():file_sha(p) for p in gates},
        'no_retry':True,
        'K175_paused':True, 'K168_authorized':False, 'deadline_remaining_24_authorized':False,
        'process_termination_grace_not_research_seconds':5,
    }
    # Put immutable pre-run copies outside OUT, which the original controller creates exclusively.
    for rel,p in paths.items():
        snap=PRE/'execution_source_snapshot'/rel
        snap.parent.mkdir(parents=True,exist_ok=True)
        with snap.open('xb') as f:
            f.write(p.read_bytes())
    write_new(declaration,decl)
    print(json.dumps({'declaration':str(declaration),'sha256':file_sha(declaration),
                      'frozen_files':len(expected),'scientific_calls':0},ensure_ascii=False))

if __name__=='__main__':
    a=argparse.ArgumentParser()
    a.add_argument('--gate', action='append',type=Path,required=True)
    freeze(a.parse_args().gate)
