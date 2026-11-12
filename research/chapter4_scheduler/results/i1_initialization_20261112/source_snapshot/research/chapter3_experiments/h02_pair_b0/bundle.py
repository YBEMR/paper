"""Minimal source-only deployment; never copy H config, results or test data."""
from pathlib import Path
import json,hashlib
from h02_pair_preflight.common import require,sha
from .io_contract import CORE,HERE,digest_file,atomic_json,load_json
CORE_FILES=('heuristic_runner.py','auto_heuristic_policy.py','control_policy.py','q1_case.py','inputs.py','start_domain.py','schedules.py','thermal.py','timing.py','heft_method.py','partial_bounds.py','scene_adapter.py')
A_FILES=('__init__.py','common.py','receipts.py','paired_response_input_view.py','paired_heuristic_entry.py','contracts.py')
B_FILES=('__init__.py','io_contract.py','exports.py','boundary.py','backends.py','budget.py','classification.py','worker.py','controller.py','bundle.py')

def runtime_sources():
    paths={str(Path('research/chapter3_experiments')/p).replace('\\','/'):CORE/p for p in CORE_FILES}
    paths['research/v1_evaluator/interval.py']=CORE.parent/'v1_evaluator/interval.py'
    for folder,items in [('h02_pair_preflight',A_FILES),('h02_pair_b0',B_FILES)]:
        for p in items: paths['research/chapter3_experiments/'+folder+'/'+p]=CORE/folder/p
    return paths

def verify_runtime_freeze():
    manifest=load_json(HERE/'evidence/runtime_freeze.json')
    current={rel:digest_file(path) for rel,path in runtime_sources().items()}
    require(current==manifest['source_files_sha256'],'FROZEN_RUNTIME_SOURCE_DRIFT')
    require({name:digest_file(HERE/name) for name in ('policy.json','execution_gate.json')}==manifest['policy_files_sha256'],'FROZEN_POLICY_OR_AUTHORIZATION_DRIFT')
    return manifest

def build_bundle(destination):
    destination=Path(destination); require(not destination.exists(),'BUNDLE_DIRECTORY_REUSED')
    freeze=verify_runtime_freeze(); destination.mkdir(parents=True)
    for rel,src in runtime_sources().items():
        target=destination/rel; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(src.read_bytes())
    for name in ('policy.json','execution_gate.json'):
        target=destination/'research/chapter3_experiments/h02_pair_b0'/name
        target.write_bytes((HERE/name).read_bytes())
    atomic_json(destination/'runtime_manifest.json',freeze)
    require(not list(destination.rglob('config_v01.json')),'H_CONFIG_MUST_NOT_BE_DEPLOYED')
    require(not list(destination.rglob('*input*json')),'NO_PREEXISTING_INPUT_OR_RESULTS_IN_CODE_BUNDLE')
    return {'bundle_sha256':sha(freeze),'worker':str(destination/'research/chapter3_experiments/h02_pair_b0/worker.py')}
