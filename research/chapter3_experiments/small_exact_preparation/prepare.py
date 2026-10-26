"""Write the K193 unapproved proposal and immutable static coverage manifest.

No `run` action exists. This script cannot start a thermal/optimization batch.
"""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contract as c
from whole_forwarding import audit


def save(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def prepare(out, subject_sha):
    if len(subject_sha) != 40 or any(v not in '0123456789abcdef' for v in subject_sha):
        raise ValueError('Need an exact 40-character hexadecimal planning subject SHA')
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    # Check immutable K192 frozen input against its actual precheck declaration.
    prior = json.loads((c.INPUT.parent / 'precheck_protocol.json').read_bytes())
    relative = c.INPUT.relative_to(c.ROOT).as_posix()
    if c.digest(c.INPUT) != prior['source_and_frozen_sha256'][relative]:
        raise ValueError('K192 restricted input drift')
    instance, config = (json.loads(path.read_bytes()) for path in [c.INPUT, c.CONFIG])
    manifest, counts = c.make_manifest(instance, config)
    manifest_path = out / 'scene_manifest.jsonl'
    with manifest_path.open('x', encoding='utf-8', newline='\n') as stream:
        for row in manifest:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(',', ':'))+'\n')
    save(out / 'domain_counts.json', counts)
    # Every discarded option must be provably late, never a local preference.
    from fractions import Fraction as Q
    options = c.expand_options(instance, config)
    late = [row for row in options if Q(row['end_ms']) > Q(row['request_deadline_ms'])]
    retained = [row for row in options if row not in late]
    keys = lambda row: (row['scenario_id'], row['stage_instance_id'], row['unit_id'], row['opp_id'], row['start_ms'])
    retained_keys = {keys(row) for row in retained}
    for row in manifest:
        for pick in row['candidate']['scenes'][row['scene_id']]:
            if (row['scene_id'], pick['stage_id'], pick['unit'], pick['opp'], pick['start_ms']) not in retained_keys:
                raise ValueError('Deadline filter removes a statically legal complete schedule')
    whole = audit()
    save(out / 'whole_forwarding_fixture.json', whole)
    native_reference_path = c.PRODUCTION / 'results/whole_long_budget01/method/matlab/request_000001.response.json'
    native_options = json.loads(native_reference_path.read_bytes())['options']
    native_options.pop('MaxTime')
    save(out / 'static_checks.json', {'state':'PASS',
        'manifest_entries':len(manifest), 'unique_scene_candidates':len({r['id'] for r in manifest}),
        'all_1550_pass_independent_and_common_static_legality':True,
        'raw_options':len(options), 'deadline_removed_count':len(late), 'retained_options':len(retained),
        'deadline_removed_option_ids':[r['option_id'] for r in late],
        'all_274500_joint_arrangements_preserved_by_deadline_filter':True,
        'new_solver_calls':0, 'new_thermal_integrations':0, 'numerical_model_built':False,
        'preparation_note':'Initial wrapper fixture used inaccessible sandbox temporary path; switched to workspace temporary folder before any scientific call. Pure fixture only.'})
    protocol = {'protocol':'K193-full-chain-small-exact-reference-proposal-v1',
        'created_utc':datetime.now(timezone.utc).isoformat(), 'planning_subject_sha':subject_sha,
        'authorized':False, 'execution_enabled':False, 'execution_launcher_implemented':False,
        'material_passport':{'mode':'plan','status':'PREPARED_NOT_EXECUTED','evidence':'K192 input and static code checks, no new research calls'},
        'input_path':relative,'input_sha256':c.digest(c.INPUT),
        'config_path':c.CONFIG.relative_to(c.ROOT).as_posix(),'config_sha256':c.digest(c.CONFIG),
        'manifest_sha256':c.digest(manifest_path),'manifest_count':1550,
        'order':'fixed round-robin over AB/CPU1,AB/NPU0,AC/CPU1,AC/NPU0; numeric canonical order within group; no energy-based reordering',
        'epsilon_J':'0.000001', 'whole_raw_option_count':78,
        'enum_proposal':{'authorized':False,'batch_runs_at_most':1,
            'scene_evaluations_at_most':1550,'per_scene_seconds_at_most':10,
            'root_seconds_at_most':2400,'calendar_seconds_at_most':2700,
            'optimizer_calls':0,'MATLAB_starts':0,'retry_or_automatic_resume':False,
            'deadline':'shared absolute root; per-scene cutoff=min(call start+10s,root deadline)',
            'old_precheck_receipt_or_cache_reuse':False,
            'ordinary_unresolved':'retain [0,+infinity], continue next fixed manifest entry if root remains',
            'technical_error':'stop batch, retain timely evidence, no replacement or retry',
            'receipt_admission':'Match request/input/candidate/source hashes and original physical validity. Keep completed inner scene SAFE or strict point violation formed before both cutoffs even if outer return is late. Reject post-cutoff new energy; prefix energy is never rankable.',
            'summary':'SAFE energy interval; certified violation excluded; unresolved/not-started [0,+infinity]; match A deployment then apply original 1/2 weights once'},
        'whole_proposal':{'authorized':False,'method_runs_at_most':1,
            'method_seconds_at_most':300,'post_SAFE_checks_at_most':1,'post_seconds_at_most':60,
            'calendar_seconds_at_most':480,'numeric_version':'original_whole_small_v1_not_augmented',
            'builder_flags':whole['final_builder_flags'], 'feedback_kind':'conditional',
            'outer_round_limit':50,'native_cut_max_iterations':10,
            'native_options_reference':{'path':native_reference_path.relative_to(c.ROOT).as_posix(),
                'sha256':c.digest(native_reference_path), 'options_except_MaxTime':native_options,
                'MaxTime':'derived only from this invocation remaining root budget',
                'engine':'original MATLAB R2023b, verify native identity before approved launch'},
            'root_scope':'fresh input/hash/initialization/model/MATLAB/solve/continuous checks/feedback all billed',
            'inherit_enum_best_or_precheck_SAFE':False,
            'stage_gate':'separate user approval, accepted exact-reference result, source/input/option identity and full launcher lifecycle fixtures before launch',
            'same_budget_ranking_against_enumeration':False},
        'separate_work':'Mainline 8 E1 thermal objective/E2 heterogeneity/E3 shared deployment/E4 deadlines and request scale continue under their own protocols and approval; this reference does not replace or authorize them',
        'paused':['K168','deadline remaining 24','large 3600s retry','HEFT/C small-domain quality runs'],
        'before_execution_still_required':['user approval of specific stage budget','one-shot supervised launcher and manifest ledger','inner evidence deadline fixtures','all transitive source/native identity freeze and host/resource checks']}
    save(out/'protocol_proposal.json',protocol)
    return protocol


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--subject-sha',required=True)
    args=parser.parse_args()
    proposal=prepare(args.out,args.subject_sha)
    print(json.dumps({'state':'PURE_PROTOCOL_PREPARATION_PASS','authorized':proposal['authorized'],
                      'manifest_count':proposal['manifest_count'],'thermal_integrations':0,'optimizer_calls':0}))
