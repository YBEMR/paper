"""K170 diagnostic-device-layer and one extra arithmetic chain declaration."""
from pathlib import Path
import json
import prepare_probes as audit

HERE=Path(__file__).resolve().parent

def main():
    frozen=audit.read(HERE/'frozen_probes.json')
    units={};sources={}
    for case in frozen['cases']:
        p=audit.locate(case['case'],'anchor_linked4','result.json');result=audit.read(p)
        units[case['case']]=result['condition']['seed_options_by_scene']
        sources[case['case']]={'path':p.relative_to(audit.REPO).as_posix(),'sha256':audit.sha(p),
            'declared_shared_deployment':result['shared_deployment']}
    classified=[]
    for p in frozen['probes']:
        if p['kind']=='single_stage_copy_mode':
            old=units[p['case']][p['scenario_id']][p['stage_instance_id']]['unit']
        else:
            old=sources[p['case']]['declared_shared_deployment'][p['shared_stage_id']]
        classified.append({'probe_id':p['probe_id'],'within_existing_linked_device_layer':p['unit_id']==old,
            'original_fixed_unit':old,'not_an_actual_search_visit':True})
    audit.save('probe_scope.json',{'protocol':'K170-fixed-device-layer-compatibility-only-v1',
        'frozen_probes_sha256':audit.sha(HERE/'frozen_probes.json'),'sources':sources,
        'probe_scope':classified,'counts':{'compatible_device_layer':sum(x['within_existing_linked_device_layer'] for x in classified),
            'outside_device_layer':sum(not x['within_existing_linked_device_layer'] for x in classified)},
        'does_not_prove_full_partial_domain_is_in_method_neighborhood':True})
    case=next(c for c in frozen['cases'] if c['case']=='base__R1')
    instance=audit.read(audit.REPO/case['instance_path'])
    scene=next(s for s in instance['scenarios'] if s['application_pair']==['A','B'])
    choose={'A.pre':'CPU1','A.main':'CPU2','A.post':'CPU1'}
    assignment={}
    for shared,uid in choose.items():
        copy=next(s['id'] for s in scene['stage_instances'] if s['shared_stage_id']==shared)
        assert any(m['unit_id']==uid and m['opp_id']=='H' for m in instance['stage_modes'][shared])
        assignment[copy]={'unit':uid,'opp':'H'}
    audit.save('conditional_chain_probe.json',{'protocol':'K170-predeclared-single-chain-arithmetic-v1',
        'case':'base__R1','instance_file_sha256':case['instance_file_sha256'],
        'partial':{'by_scene':{scene['id']:assignment}},
        'expected':'forced_residency_lower_bound_J >= capacity_lower_bound_J; strict improvement separately reported',
        'within_existing_linked_device_layer':False,'reason':'A.main maps CPU2 instead of declared NPU0',
        'included_in_490_probe_statistics':False,'start_times_generated':False,
        'new_workload_or_parameters':False,'scientific_calls':0})
    print({'probes':len(classified),'device_compatible':sum(x['within_existing_linked_device_layer'] for x in classified),
        'extra_chain_probes':1,'scientific_calls':0})

if __name__=='__main__':main()
