"""K196 read-only environment/source gate; no MATLAB or research call."""
from pathlib import Path
import importlib.metadata
import json
import platform
import sys

ROOT=Path.cwd()
HERE=ROOT/'research/chapter3_experiments/small_whole_execution'
PREP=ROOT/'research/chapter3_experiments/results/small_whole_preparation01'
OUT=ROOT/'research/chapter3_experiments/results/small_whole_execution01'
sys.path.insert(0,str(HERE))
import run_once as r

plan=r.read(PREP/'plan.json')
if r.digest(PREP/'plan.json')!='75f692f7681b294e41c7dc229c30517de4d4461da383985e6554cfa415466d5e':
    raise ValueError('Wrong frozen K195 plan')
r.verify_frozen(PREP,plan)
environment=r.read(PREP/'environment_static.json')
versions={name:importlib.metadata.version(name) for name in ('numpy','scipy','psutil')}
host,resource_ok=r.host_context()
checks={
    'python_version_same':sys.version==environment['python'],
    'python_executable_same':str(Path(sys.executable).resolve())==str(Path(environment['python_executable']).resolve()),
    'platform_same':platform.platform()==environment['platform'],
    'numpy_scipy_psutil_same':versions==environment['packages'],
    'native_executable_same':r.digest(plan['native_executable'])==plan['native_executable_sha256'],
    'live_scientific_sources_same_as_frozen':all(r.digest(ROOT/name)==expected for name,expected in plan['source_sha256'].items()),
    'K193_original_restricted_input_unchanged':r.digest(ROOT/'research/chapter3_experiments/results/small_full_chain_precheck02/restricted_input.json')==plan['payload_sha256']['input_instance.json'],
    'K193_original_config_unchanged':r.digest(ROOT/'research/chapter3_experiments/results/whole_long_budget01/method/input_config.json')==plan['payload_sha256']['input_config.json'],
    'K195_97_pure_checks_bound':r.read(PREP/'pure_checks.json')['passed'] is True and r.read(PREP/'pure_checks.json')['plan_sha256']==r.digest(PREP/'plan.json'),
    'fresh_output_absent':not OUT.exists(),
    'approval_not_consumed':not (PREP/'approval.json').exists(),
    'host_and_resources':resource_ok(host),
}
record={'protocol':'K196-K195-prelaunch-readonly-v1','utc':r.now(),'passed':all(checks.values()),
    'checks':checks,'host':host,'packages':versions,'plan_sha256':r.digest(PREP/'plan.json'),
    'source_count':len(plan['source_sha256']),'wrapper_count':len(plan['wrapper_sha256']),
    'input_sha256':plan['payload_sha256']['input_instance.json'],
    'MATLAB_starts':0,'research_calls':0,'thermal_evaluations':0,
    'actual_toolbox_checkout':'must be checked in the unique authorized method startup, no separate native preflight',
    'K194_best_candidate_or_cache_loaded':False}
r.write_new(PREP/'prelaunch_k196.json',record)
print(json.dumps(record,ensure_ascii=False))
raise SystemExit(0 if record['passed'] else 3)
