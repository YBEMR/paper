from copy import deepcopy
from functools import partial
import json
import time
from run_four_method_comparison import canonical, save, settings
from deadline_entry import jobs, fresh_input
SECONDS, SCENE_SECONDS, CUT = 300, 60, 10

def execute(job,out,declaration,entries):
    if job not in jobs(declaration['problem_id']):raise ValueError('Unknown frozen method')
    identity={'input_verified':None};lower={}
    def loader(budget):
        raw,config,instance=fresh_input(declaration['problem_id'],budget)
        actual=dict(zip(('raw_config_sha256','config_sha256','input_sha256'),
                        map(canonical,(raw,config,instance))))
        identity['input_verified']=actual==declaration['input_identities']
        if identity['input_verified'] is not True:raise ValueError('Fresh billed input changed')
        if job['method']=='milp':
            from partial_bounds import independent_lower_bound
            folder.mkdir(parents=True,exist_ok=True)
            save(folder/'method_budget_identity.json',{'start':budget.start,
                'deadline':budget.deadline,'limit_s':SECONDS,'clock':'monotonic'})
            with budget.phase('comparison_independent_lower_bound'):
                lower['L0']=independent_lower_bound(instance,None,budget)
        budget.check();return config,instance
    folder=out/job['id'];factory=partial(entries['session'],cut_max_iterations=CUT)
    if job['method']=='milp':
        result=entries['whole'](loader,folder,seconds=SECONDS,feedback_kind='conditional',
            model_builder=partial(entries['builder'],prefilter_deadlines=True,cumulative_precedence=False),
            session_factory=factory)
    elif job['method']=='linked_fixed_unit_opp_start':
        # Identical K151 root start: internal lazy setup is billed.
        from timing import MethodBudget
        budget=MethodBudget(float(SECONDS),clock=time.monotonic)
        shared,build=settings()
        def update(r,record):
            print(json.dumps({'event':'SAFE_AGGREGATE_UPDATE','method':job['id'],
                'elapsed_s':record['committed_at_s'],'U_J':record['safe_upper_bound_J']}),flush=True)
        result=entries['linked'](loader,folder,seconds=SECONDS,budget=budget,clock=budget.clock,
            shared_deployment=shared,scene_slice_s=SCENE_SECONDS,builder_options=build,
            session_factory=factory,opened_by_scene=deepcopy(declaration['first_opened_by_scene']),
            linked_opened_by_scene=deepcopy(declaration['linked_opened_by_job'][job['id']]),
            on_global_update=update,preeliminate_closed_anchors=True)
    else:
        result=entries['heuristic'](loader,folder,method=job['method'],seconds=SECONDS,
                                    seed=job['seed'],allow_auto_low=True)
    if lower:save(folder/'independent_bounds.json',lower)
    return result,identity
