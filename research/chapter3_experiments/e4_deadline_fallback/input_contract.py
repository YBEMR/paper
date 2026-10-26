"""Static same-input contract, never run search or thermal functions."""
from copy import deepcopy
from control_policy import with_auto_low_idle
from inputs import load_config,build_instance
from e1_objective.execution_io import sha,require
from .protocol import PROBLEM_ID,METHODS

def prepare_inputs():
    c=with_auto_low_idle(load_config())
    return {PROBLEM_ID:dict(config=c,instance=build_instance(c,PROBLEM_ID),objective='FULL')}

def validate_inputs(packets):
    require(isinstance(packets,dict) and set(packets)=={PROBLEM_ID},'ONE_IDENTICAL_FROZEN_PROBLEM')
    p=packets[PROBLEM_ID];expected=prepare_inputs()[PROBLEM_ID]
    require(set(p)=={'config','instance','objective'} and p==expected,'FROZEN_DOUBLE_REQUEST_INPUT_DRIFT')
    i=p['instance']
    return dict(state='STATIC_IDENTICAL_INPUT_PASSED',problem_id=PROBLEM_ID,
        packet_sha256=sha(p),input_sha256=sha(i),config_sha256=sha(p['config']),
        methods=list(METHODS),same_scientific_packet_both_slots=True,method_field_in_scientific_packet=False,
        requests_per_application=i['settings']['requests_per_application'],
        stage_executions_across_alternative_scenarios=sum(len(s['stage_instances']) for s in i['scenarios']),
        original_generator_used=True,candidate_search_performed=False,thermal_propagation_performed=False,new_real_SAFE=0)
