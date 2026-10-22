"""Freeze K170 read-only branch probes, P0 reference U and integrity baseline."""
import csv
from fractions import Fraction as F
import hashlib
import io
import json
from pathlib import Path
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
REPO=HERE.parents[4]
RESULTS=ROOT/'results'
SEEN={}

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as s:
        while b:=s.read(1048576):h.update(b)
    return h.hexdigest()
def read(p):
    p=Path(p);data=p.read_bytes();SEEN[p.relative_to(REPO).as_posix()]=hashlib.sha256(data).hexdigest()
    return json.loads(data.decode('utf-8-sig'))
def save(name,value):
    with (HERE/name).open('x',encoding='utf-8') as s:json.dump(value,s,ensure_ascii=False,indent=2);s.write('\n')
def locate(case,method,name):
    paths=[RESULTS/g/'calls'/case/method/name for g in ('p0_execution01','p0_resume01')]
    existing=[p for p in paths if p.is_file()]
    if len(existing)!=1:raise ValueError('Expected one original '+case+'/'+method+'/'+name)
    return existing[0]
def different(mapping):return [p for p,h in mapping.items() if not (REPO/p).is_file() or sha(REPO/p)!=h]

def main():
    started=time.perf_counter()
    before169=read(RESULTS/'mainline_mechanism_audit01/review/before_manifest.json')
    k168=RESULTS/'whole_native_diagnostic_precheck01/run01/real_preparation'
    declaration=read(k168/'declaration.json')
    old_sources={p:sha(REPO/p) for p in declaration['source_sha256']}
    assert all(old_sources[p]==h for p,h in declaration['source_sha256'].items())
    prior={k:before169[k] for k in ('prior_artifact_sha256','target_sha256',
        'original16_call_files_sha256','ledger_declaration_terminal_sha256','K168_pending_sha256')}
    assert not any(different(m) for m in prior.values())
    k169_files={p.relative_to(REPO).as_posix():sha(p)
        for p in sorted((RESULTS/'mainline_mechanism_audit01').rglob('*')) if p.is_file()}
    slots=read(RESULTS/'deadline_execution01/declaration.json')['slots']
    unexpected=[]
    for slot in slots[16:]:
        for camp in ('deadline_execution01','deadline_resume01'):
            p=RESULTS/camp/'claims'/(slot['slot_id']+'.json')
            if p.exists():unexpected.append(p.relative_to(REPO).as_posix())
    assert not unexpected and len(slots[16:])==24
    assert declaration['plan']['authorized'] is False and declaration['research_calls_consumed']==0
    save('before_manifest.json',{'protocol':'K170-independent-before-v1','source_sha256':old_sources,
        'source_count':len(old_sources),**prior,'K169_finalization_sha256':k169_files,
        'consumed_original':16,'unstarted_original':24,'unexpected_claims':unexpected,
        'new_audit_target_excluded':HERE.parent.relative_to(REPO).as_posix(),
        'scientific_calls':0,'K168_pending':True})
    csvpath=RESULTS/'p0_resume01/analysis01/results40.csv'
    data=csvpath.read_bytes();SEEN[csvpath.relative_to(REPO).as_posix()]=hashlib.sha256(data).hexdigest()
    rows=list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))
    assert len(rows)==40
    references=[]
    for sample in range(1,6):
        case='base__R'+str(sample);selected=[r for r in rows if r['problem_id']==case]
        assert len(selected)==8
        values=[]
        for row in selected:
            assert row['post_SAFE']=='True' and row['comparison_usable']=='True'
            path=locate(case,row['method'],'result.json');raw=read(path)
            assert raw['state']=='SAFE' and raw.get('safe_upper_bound_J') is not None
            U=F(raw['safe_upper_bound_J']);assert U==F(row['safe_U_exact'])
            values.append({'method':row['method'],'U_exact_J':str(U),
                'source_path':path.relative_to(REPO).as_posix(),'source_sha256':SEEN[path.relative_to(REPO).as_posix()],
                'post_SAFE_as_archived':True,'comparison_usable_as_archived':True,
                'post_recomputed':False,'candidate_or_witness_exported':False})
        best=min(F(v['U_exact_J']) for v in values)
        references.append({'case':case,'reference_U_exact_J':str(best),
            'reference_methods':[v['method'] for v in values if F(v['U_exact_J'])==best],
            'all8_original_U':values,'use':'posthoc arithmetic exclusion only; never a new method initial witness'})
    save('reference_U.json',{'protocol':'K170-posthoc-P0-original-U-v1','cases':references,
        'CSV_sha256':sha(csvpath),'old_U_count':40,'new_SAFE_U':0,'reevaluation_calls':0})
    probes=[];cases=[]
    for sample in range(1,6):
        case='base__R'+str(sample)
        path=RESULTS/'p0_batch_preparation01/inputs'/case/'instance.json'
        instance=read(path)
        sourcehash=SEEN[path.relative_to(REPO).as_posix()]
        scene_counts={};copy_count=0
        for scene in sorted(instance['scenarios'],key=lambda s:s['id']):
            for stage in sorted(scene['stage_instances'],key=lambda s:s['id']):
                for mode in sorted(instance['stage_modes'][stage['shared_stage_id']],key=lambda m:m['mode_id']):
                    probes.append({'probe_id':f'{case}::copy_mode::{stage["id"]}::{mode["mode_id"]}',
                        'case':case,'kind':'single_stage_copy_mode','scenario_id':scene['id'],
                        'stage_instance_id':stage['id'],'shared_stage_id':stage['shared_stage_id'],
                        'mode_id':mode['mode_id'],'unit_id':mode['unit_id'],'opp_id':mode['opp_id'],
                        'shared_unit_implication':'all copies of this shared identity use this unit; other-copy OPPs remain free'})
                    copy_count+=1;scene_counts[scene['id']]=scene_counts.get(scene['id'],0)+1
        common=set.intersection(*({s['shared_stage_id'] for s in scene['stage_instances']} for scene in instance['scenarios']))
        assert common=={'A.pre','A.main','A.post'}
        shared_count=0
        for shared in sorted(common):
            for uid in sorted({m['unit_id'] for m in instance['stage_modes'][shared]}):
                probes.append({'probe_id':f'{case}::shared_unit::{shared}::{uid}',
                    'case':case,'kind':'single_shared_unit','shared_stage_id':shared,'unit_id':uid,
                    'opp_fixed':False,'start_fixed':False})
                shared_count+=1
        cases.append({'case':case,'instance_path':path.relative_to(REPO).as_posix(),
            'instance_file_sha256':sourcehash,'stage_copy_mode_probes':copy_count,
            'copy_modes_by_scene':scene_counts,'shared_unit_probes':shared_count,
            'root_bound_rows_separate':1})
    assert len(probes)==490 and len({p['probe_id'] for p in probes})==490
    save('frozen_probes.json',{'protocol':'K170-predeclared-one-level-arithmetic-probes-v1',
        'cases':cases,'probes':probes,'probe_count':490,'root_rows_separate':5,
        'selection_rule':'Every original mode of every Stage copy, plus every legal unit of each shared A Stage; no outcome filtering.',
        'not_actual_search_trace':True,'not_disjoint_partition_or_domain_coverage_count':True,
        'start_times_or_schedules_generated':False,'new_scientific_calls':0,
        'cost_protocol':{'repetitions':3,'case_order':'R1,R2,R3,R4,R5',
            'probe_order':'frozen_probes list order, unchanged across repetitions',
            'cold':'new prepared context and root bound, 3 independent repeats per case',
            'warm':'prepared context plus one root warm-up outside measured interval, then all frozen probes for that case, 3 repeats',
            'file_read_and_hash':'separate; not included in pure bound timings',
            'no_adaptive_repetition_or_best_only_reporting':True,'claim':'bound arithmetic only; no solver speedup claim'}})
    save('preparation_record.json',{'protocol':'K170-independent-freeze-record-v1',
        'preparation_io_hash_and_manifest_wall_s':time.perf_counter()-started,
        'read_artifact_sha256':SEEN,'files':{n:sha(HERE/n) for n in ('before_manifest.json','reference_U.json','frozen_probes.json')},
        'reference_U_for_arithmetic_only':True,'cost_experiment_started':False,
        'new_models':0,'new_schedules':0,'solver_calls':0,'thermal_or_post_calls':0})
    print({'old_sources':len(old_sources),'K169_artifacts':len(k169_files),'U_records':40,
        'copy_mode_probes':450,'shared_unit_probes':40,'all_probes':490,'repetitions_fixed':3,'scientific_calls':0})

if __name__=='__main__':main()
