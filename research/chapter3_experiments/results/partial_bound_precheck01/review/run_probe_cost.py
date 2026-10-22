"""K170 frozen one-level arithmetic probes and fixed three-repeat cost audit."""
from collections import Counter
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
import traceback

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
REPO=HERE.parents[4]
SOURCE=ROOT/'conditional_energy_bound/bounds.py'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def save(p,value):
    with Path(p).open('x',encoding='utf-8') as s:json.dump(value,s,ensure_ascii=False,indent=2);s.write('\n')
def identity(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def partial_of(p):
    if p['kind']=='single_shared_unit':return {'shared_units':{p['shared_stage_id']:p['unit_id']}}
    return {'by_scene':{p['scenario_id']:{p['stage_instance_id']:{'unit':p['unit_id'],'opp':p['opp_id']}}}}
def descriptive(values):
    return {'three_values_s':values,'median_s':statistics.median(values),'min_s':min(values),'max_s':max(values)}

def main(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    frozen_paths=[HERE/n for n in ('frozen_probes.json','reference_U.json','probe_scope.json','conditional_chain_probe.json','probe_protocol.md','deadline_scope.json','cost_guard_revision.json')]
    source_before=sha(SOURCE);frozen_hash={p.name:sha(p) for p in frozen_paths}
    blocked={'scientific_import':0,'process_launch':0}
    forbidden={'numpy','scipy','milp','thermal','inputs','schedules','scene_adapter','matlab_bridge',
        'initial_point','initial_schedule','formal_milp','partial_bounds','milp_coefficients'}
    active={'value':True}
    class GuardViolation(KeyboardInterrupt):pass
    def deny(kind,message):
        blocked[kind]+=1;raise GuardViolation(message)
    def audit(event,args):
        if not active['value']:return
        if event=='import' and str(args[0]).split('.')[0] in forbidden:deny('scientific_import',str(args[0]))
        if event in ('subprocess.Popen','os.system','os.startfile','os.posix_spawn'):deny('process_launch',event)
    science_before=sorted(n for n in sys.modules if n.split('.')[0] in forbidden)
    sys.addaudithook(audit)
    record={'protocol':'K170-fixed490-three-repeat-bound-cost-v1','source_sha256_before':source_before,
        'frozen_files_sha256':frozen_hash,'repetitions':3,'case_results':[],'error':None}
    bound_calls=0;decision_calls=0;prepare_calls=0;reference_calls=0
    try:
        assert source_before=='9b4fc402a00c71d9f919c3829df0b43277df614fbd5fcfe2aec6d67de02c6e0a'
        assert not science_before
        sys.path.insert(0,str(ROOT/'conditional_energy_bound'))
        import bounds as api
        assert Path(api.__file__).resolve()==SOURCE.resolve()
        t=time.perf_counter()
        frozen,refs,scopes,chain=map(read,frozen_paths[:4])
        instances={}
        for case in frozen['cases']:
            path=REPO/case['instance_path']
            assert sha(path)==case['instance_file_sha256']
            instances[case['case']]=read(path)
        record['input_and_frozen_read_hash_wall_s']=time.perf_counter()-t
        references={r['case']:r for r in refs['cases']}
        layer={r['probe_id']:r['within_existing_linked_device_layer'] for r in scopes['probe_scope']}
        deadline={r['probe_id']:r['already_excluded_by_ordinary_deadline_necessity'] for r in read(HERE/'deadline_scope.json')['rows']}
        all_rows=[];first_receipts={}
        for case in frozen['cases']:
            case_id=case['case'];instance=instances[case_id]
            probes=[p for p in frozen['probes'] if p['case']==case_id]
            partials=[partial_of(p) for p in probes]
            cold=[];warm=[];root_bounds=[]
            for repetition in range(3):
                a=time.perf_counter();ctx=api.prepare(instance);prepare_calls+=1;b=time.perf_counter()
                root=ctx.bound();bound_calls+=1;c=time.perf_counter()
                cold.append({'repetition':repetition+1,'prepare_s':b-a,'root_bound_s':c-b,'total_s':c-a})
                root_bounds.append(dict(root))
            assert len({identity(r) for r in root_bounds})==1
            selected=references[case_id]
            method=selected['reference_methods'][0]
            source=next(x for x in selected['all8_original_U'] if x['method']==method)
            path=REPO/source['source_path'];assert sha(path)==source['source_sha256']
            a=time.perf_counter();reference=ctx.reference_from_archive(path,path.parent/'postcheck.json');reference_calls+=1;b=time.perf_counter()
            test_ref=api.pruning_decision(root,reference);decision_calls+=1
            assert F(test_ref['archived_upper_bound_J'])==F(selected['reference_U_exact_J'])
            current={'case':case_id,'input_sha256':ctx.input_sha256,'probe_count':len(probes),
                'root_bound':dict(root),'root_reference_decision':test_ref,'reference_source_path':source['source_path'],
                'reference_archive_admission_IO_hash_s':b-a,'cold':cold,'warm':warm}
            for repetition in range(3):
                a=time.perf_counter();ctx=api.prepare(instance);prepare_calls+=1;b=time.perf_counter()
                warm_root=ctx.bound();bound_calls+=1;c=time.perf_counter()
                times=[];bound_sum=0.;decision_sum=0.
                for p,partial in zip(probes,partials):
                    a0=time.perf_counter();receipt=ctx.bound(partial);bound_calls+=1;b0=time.perf_counter()
                    decision=api.pruning_decision(receipt,reference);decision_calls+=1;c0=time.perf_counter()
                    bound_sum+=b0-a0;decision_sum+=c0-b0
                    times.append({'probe_id':p['probe_id'],'bound_s':b0-a0,'decision_s':c0-b0,'joint_s':c0-a0})
                    if repetition==0:
                        first_receipts[p['probe_id']]=identity({'bound':dict(receipt),'decision':decision})
                        all_rows.append({'probe_id':p['probe_id'],'case':case_id,'kind':p['kind'],'partial':partial,
                            'within_existing_linked_device_layer':layer[p['probe_id']],
                            'already_excluded_by_ordinary_deadline_necessity':deadline[p['probe_id']],
                            'legacy_form_conditioned_algebra_prunes':F(receipt['legacy_conditioned_lower_bound_J'])>F(selected['reference_U_exact_J']),
                            'bound':dict(receipt),'decision':decision,
                            'new_bound_minus_legacy_J':str(F(receipt['lower_bound_J'])-F(receipt['legacy_conditioned_lower_bound_J'])),
                            'forced_minus_capacity_J':str(F(receipt['forced_residency_lower_bound_J'])-F(receipt['capacity_lower_bound_J']))})
                    else:
                        assert first_receipts[p['probe_id']]==identity({'bound':dict(receipt),'decision':decision})
                warm.append({'repetition':repetition+1,'prepare_outside_warm_s':b-a,'root_warmup_outside_warm_s':c-b,
                    'pure_bound_sum_s':bound_sum,'pure_decision_sum_s':decision_sum,'pure_joint_sum_s':bound_sum+decision_sum,
                    'per_probe':times})
            current['cold_total_statistics']=descriptive([x['total_s'] for x in cold])
            current['warm_bound_statistics']=descriptive([x['pure_bound_sum_s'] for x in warm])
            current['warm_decision_statistics']=descriptive([x['pure_decision_sum_s'] for x in warm])
            current['warm_joint_statistics']=descriptive([x['pure_joint_sum_s'] for x in warm])
            rows=[r for r in all_rows if r['case']==case_id]
            current['decisions']=dict(Counter(r['decision']['decision'] for r in rows))
            current['device_layer_decisions']={str(flag):dict(Counter(r['decision']['decision'] for r in rows
                if r['within_existing_linked_device_layer']==flag)) for flag in (True,False)}
            current['new_prunes_after_ordinary_deadline']=sum(r['decision']['prune'] and not r['already_excluded_by_ordinary_deadline_necessity'] for r in rows)
            current['new_prunes_beyond_legacy_algebra_and_deadline']=sum(r['decision']['prune'] and not r['legacy_form_conditioned_algebra_prunes'] and not r['already_excluded_by_ordinary_deadline_necessity'] for r in rows)
            record['case_results'].append(current)
        ctx=api.prepare(instances[chain['case']]);prepare_calls+=1
        receipt=ctx.bound(chain['partial']);bound_calls+=1
        assert F(receipt['forced_residency_lower_bound_J'])>=F(receipt['capacity_lower_bound_J'])
        record['separate_chain']={'declaration_sha256':sha(HERE/'conditional_chain_probe.json'),
            'bound':dict(receipt),'forced_minus_capacity_J':str(F(receipt['forced_residency_lower_bound_J'])-F(receipt['capacity_lower_bound_J'])),
            'within_existing_linked_device_layer':False,'included_in490':False}
        record['probes']=all_rows
        record['all_probe_decisions']=dict(Counter(r['decision']['decision'] for r in all_rows))
        assert len(all_rows)==490 and bound_calls==1501 and prepare_calls==31 and reference_calls==5
    except BaseException:
        record['error']=traceback.format_exc()
    finally:
        active['value']=False
    science_after=sorted(n for n in sys.modules if n.split('.')[0] in forbidden)
    record.update(source_sha256_after=sha(SOURCE),frozen_files_sha256_after={p.name:sha(p) for p in frozen_paths},
        prepare_calls=prepare_calls,arithmetic_bound_calls=bound_calls,arithmetic_decision_calls=decision_calls,
        archive_reference_admissions=reference_calls,guard={'blocked_attempts':blocked,'all_zero':not any(blocked.values()),
            'scientific_modules_before':science_before,'scientific_modules_after':science_after,
            'function_profile_enabled':False,'strategy':'Audit scientific imports and processes; source/frozen hashes and empty science modules. Full function-entry guards tested separately.'},
        new_models=0,new_schedules=0,solver_calls=0,thermal_or_post_calls=0,
        scope='Posthoc overlapping one-layer arithmetic probes, not actual search traces or a solve-time speedup experiment.')
    record['passed']=record['error'] is None and record['source_sha256_before']==record['source_sha256_after'] and record['frozen_files_sha256']==record['frozen_files_sha256_after'] and not any(blocked.values()) and not science_after
    save(out/'results.json',record)
    print({'passed':record['passed'],'error':record['error'],'bound_calls':bound_calls,
        'probe_decisions':record.get('all_probe_decisions'),'source_unchanged':record['source_sha256_before']==record['source_sha256_after'],
        'scientific_entry_attempts':blocked})
    if not record['passed']:raise SystemExit(1)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--out',required=True)
    main(p.parse_args().out)
