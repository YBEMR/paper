"""Read-only analysis of a completed K119 CutMaxIterations 10/1 pair.

No production module is imported. scipy/numpy only read and fingerprint
published MAT arrays; matplotlib only draws stored in-budget evidence.
This is one fixed shared deployment, not a search over the sixteen conditions.
"""
import argparse
import csv
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path


ANALYSIS_SCOPE = 'fixed_shared_deployment_not_global16'
PROTOCOL = 'partial-shared-deployment-unweighted-scene-v1'
MODEL_FIELDS = ('c','A','b','Aeq','beq','lb','ub','intcon')


def _hash(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,
        separators=(',',':'),allow_nan=False).encode('utf-8')).hexdigest()


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def _q(value):
    if isinstance(value,bool) or not isinstance(value,(str,int,F)):
        raise ValueError('Expected exact saved energy')
    return F(value)


def _interval(value):
    if not isinstance(value,list) or len(value) != 2: raise ValueError('No saved energy interval')
    lo,hi = map(_q,value)
    if lo > hi: raise ValueError('Reversed saved interval')
    return lo,hi


def _timely(value,limit):
    return (isinstance(value,(int,float)) and not isinstance(value,bool)
            and math.isfinite(value) and 0 <= value < limit)


def interval_comparison(initial,final):
    """Upper-bound reduction and strict true-energy separation stay distinct."""
    if initial is None or final is None:
        return {'upper_bound_improved':None,'strict_improvement_certified':None}
    lo,hi = _interval(initial); _,final_hi = _interval(final)
    return {'upper_bound_improved':final_hi < hi,'strict_improvement_certified':final_hi < lo}


def first_strict_time(initial,updates):
    if initial is None: return None
    lower,_ = _interval(initial)
    eligible = [row['committed_at_s'] for row in updates
                if _interval(row['energy_J'])[1] < lower]
    return min(eligible,default=None)


def compare_options(left,right):
    """Preserve raw differences; only CutMaxIterations is the intended switch."""
    if not isinstance(left,dict) or not isinstance(right,dict) or not left or not right:
        return {'observed':False,'all_other_options_equal_raw':None,
                'other_settings_equal_excluding_budget_MaxTime':None,'differences':{}}
    differences = {key:{'cut10':left.get(key),'cut1':right.get(key)}
                   for key in sorted(set(left)|set(right)) if left.get(key) != right.get(key)}
    other = set(differences)-{'CutMaxIterations'}
    return {'observed':True,'all_other_options_equal_raw':not other,
            'other_settings_equal_excluding_budget_MaxTime':not (other-{'MaxTime'}),
            'differences':differences,'intended_switch_observed':
                left.get('CutMaxIterations') == 10 and right.get('CutMaxIterations') == 1}


def _candidate_hash(candidate):
    """Compare already decoded row identities; never decode a native vector."""
    if not isinstance(candidate,dict) or not isinstance(candidate.get('scenes'),dict): return None
    return _hash({'scenes':{sid:sorted(rows,key=lambda row:row['stage_id'])
                           for sid,rows in candidate['scenes'].items()}})


def _saved_safe(aggregate,instance,fixed,limit):
    """Minimal stored-receipt consistency check, with no reevaluation."""
    try:
        if not isinstance(aggregate,dict): return False
        candidate = aggregate.get('safe_candidate'); identity = aggregate.get('identity') or {}
        scenes = {scene['id'] for scene in instance['scenarios']}
        energy = _interval(aggregate['weighted_energy_J'])
        if (aggregate.get('protocol') != PROTOCOL or aggregate.get('state') != 'SAFE'
                or aggregate.get('rankable_energy') is not True
                or aggregate.get('violations') or aggregate.get('receipt_errors')
                or aggregate.get('shared_deployment') != fixed
                or not _timely(aggregate.get('completed_at_elapsed_s'),limit)
                or set(aggregate['scenes']) != scenes or set(candidate['scenes']) != scenes
                or identity.get('full_input_sha256') != _hash(instance)
                or identity.get('shared_deployment_sha256') != _hash(fixed)
                or identity.get('candidate_sha256') != _hash(candidate)
                or _q(aggregate['safe_upper_bound_J']) != energy[1]
                or aggregate.get('receipt_sha256') != _hash({key:value for key,value in aggregate.items()
                                                           if key != 'receipt_sha256'})):
            return False
        for sid,receipt in aggregate['scenes'].items():
            physical = receipt.get('result') or {}
            if (receipt.get('state') != 'SAFE' or receipt.get('rankable_energy') is not True
                    or receipt.get('violations') or not _timely(receipt.get('completed_at_elapsed_s'),limit)
                    or physical.get('state') != 'SAFE' or physical.get('complete') is not True
                    or not _timely(physical.get('completed_at_elapsed_s'),limit)
                    or physical.get('energy_accuracy_met') is not True
                    or _q(physical['covered_until_s']) != _q(instance['window_ms'])/1000):
                return False
        return True
    except (KeyError,TypeError,ValueError,ZeroDivisionError):
        return False


def _published_arrays(path):
    """Read existing arrays only; hash values, excluding runtime budgets/x0."""
    import numpy as np
    from scipy import sparse
    from scipy.io import loadmat
    values = loadmat(path,variable_names=list(MODEL_FIELDS)+['x0'])
    digests,shapes = {},{}
    for key in MODEL_FIELDS:
        value = values[key]; digest = hashlib.sha256()
        if sparse.issparse(value):
            value = value.tocsc(copy=True); value.sum_duplicates(); value.sort_indices()
            shape = list(value.shape); digest.update(b'canonical_csc')
            for array,dtype in ((value.indptr,'<i8'),(value.indices,'<i8'),(value.data,'<f8')):
                digest.update(np.asarray(array,dtype=dtype).tobytes())
        else:
            value = np.asarray(value); shape = list(value.shape)
            digest.update(np.asarray(value,dtype='<i8' if key == 'intcon' else '<f8').tobytes(order='C'))
        digest.update(json.dumps(shape).encode('ascii'))
        digests[key] = digest.hexdigest(); shapes[key] = shape
    x0 = np.asarray(values['x0'],dtype=float).ravel().tolist() if 'x0' in values else None
    return {'sha256':_hash(digests),'component_sha256':digests,'shapes':shapes,
            'scope':'published numerical model arrays; excludes runtime allocations and x0'},x0


def _vector_comparison(vector,x0):
    if not isinstance(vector,list): vector = [] if vector is None else [vector]
    if not vector: return {'length':0,'exactly_x0':None,'max_abs_delta':None}
    if x0 is None or len(vector) != len(x0):
        return {'length':len(vector),'exactly_x0':None,'max_abs_delta':None}
    return {'length':len(vector),'exactly_x0':vector == x0,
            'max_abs_delta':max(abs(float(a)-float(b)) for a,b in zip(vector,x0))}


def _request_records(invocation,result,limit):
    records = []
    for sid,scene in result.get('scenes',{}).items():
        solved = scene.get('solver_result') or {}; diagnostic = solved.get('diagnostic') or {}
        for round_index,returned in enumerate(solved.get('rounds',[]),1):
            number = returned.get('request_number')
            if not isinstance(number,int):
                records.append({'scene_id':sid,'round':round_index,'error':'NO_SAVED_REQUEST_NUMBER',
                                'native_status':returned.get('status')}); continue
            prefix = invocation/'matlab'/f'request_{number:06d}'
            python = _read(prefix.with_suffix('.python.json')) if prefix.with_suffix('.python.json').is_file() else returned
            response = _read(prefix.with_suffix('.response.json')) if prefix.with_suffix('.response.json').is_file() else returned
            inputs = _read(prefix.with_suffix('.input.json')) if prefix.with_suffix('.input.json').is_file() else {}
            fingerprint = x0 = None
            if prefix.with_suffix('.mat').is_file(): fingerprint,x0 = _published_arrays(prefix.with_suffix('.mat'))
            native_vectors = [{'source':'final','within_budget':python.get('budget_valid') is True,
                               **_vector_comparison(response.get('x'),x0)}]
            event_summaries = []
            received = {event.get('event_number'):event.get('method_elapsed_s')
                for event in diagnostic.get('solver_progress',[]) if event.get('request') == prefix.name}
            for path in sorted(prefix.parent.glob(prefix.name+'.event_*.json')):
                event = _read(path); comparison = _vector_comparison(event.get('x'),x0)
                event_summaries.append({key:value for key,value in event.items() if key != 'x'} |
                    {'x_length':comparison['length'],'received_at_method_s':received.get(event.get('event_number'))})
                if comparison['length']:
                    native_vectors.append({'source':path.name,
                        'within_budget':_timely(received.get(event.get('event_number')),limit),**comparison})
            all_vectors = [v for v in native_vectors if v['length']]
            timely = [v for v in all_vectors if v['within_budget']]
            callbacks = [e for e in event_summaries if e.get('kind') == 'callback']
            records.append({'scene_id':sid,'round':round_index,'request_number':number,
                'model_fingerprint':fingerprint,'input_initial_point':inputs.get('initial_point'),
                'native_initial_point':response.get('initial_point'),
                'native_status':response.get('status'),'exitflag':response.get('exitflag'),
                'budget_valid':python.get('budget_valid'),'accepted_for_evaluation':python.get('accepted_for_evaluation'),
                'native_options':response.get('options'),
                'native_cut_fields':{key:value for key,value in response.items() if 'cut_max' in key.lower() or 'cutmax' in key.lower()},
                'native_phase_seconds':response.get('phase_seconds'),
                'native_events':event_summaries,'native_final_output':response.get('output'),
                'first_callback_request_wall_s':callbacks[0]['request_wall_seconds'] if callbacks else None,
                'first_nonempty_callback_request_wall_s':next((e['request_wall_seconds'] for e in callbacks if e['x_length']),None),
                'native_request_wall_s':response.get('matlab_request_wall_seconds'),
                'python_solve_wall_s':python.get('wall_seconds'),
                'solver_max_time_s_used':response.get('solver_max_time_s_used'),
                'vectors_compared_to_published_x0':native_vectors,
                'different_native_vector_observed_raw':any(v['exactly_x0'] is False for v in all_vectors),
                'different_native_vector_observed_in_budget':any(v['exactly_x0'] is False for v in timely),
                'x0_reference_available':x0 is not None,
                'error_identifier':response.get('error_identifier'),'error_message':response.get('error_message'),
                'cancel_requests':diagnostic.get('cancel_requests',[]),
                'solver_reported_bounds':scene.get('solver_reported_bounds',[])})
    return records


def _call(folder,label,run_record):
    invocation = folder/'invocation'; path = invocation/'result.json'
    out = {'cut_max_iterations_declared':label,'run_record':run_record,'result_present':path.is_file(),
           'state':None,'reason':'NO_COMPLETED_RESULT','initial_energy_J':None,'final_energy_J':None,
           'final_U_J':None,'updates':[],'independent_bounds':{},'requests':[],
           'receipt_errors':[],'decoded_candidate_changes':[]}
    if not path.is_file(): return out
    result = _read(path)
    if not result.get('timing') or not result.get('reason'):
        raise ValueError('Refusing unfinished partial result: '+str(path))
    instance = _read(invocation/'input_instance.json'); config = _read(invocation/'input_config.json')
    limit = float(result['timing']['limit_s']); fixed = result.get('shared_deployment')
    out.update(state=result.get('state'),reason=result.get('reason'),error=result.get('error'),
        full_input_sha256=_hash(instance),config_sha256=_hash(config),shared_deployment=fixed,
        timing=result['timing'],budget_s=limit,stop_stage=result.get('stop_stage'),stop_scene=result.get('stop_scene'),
        scene_slice_s=result.get('scene_slice_s'),remaining_domain=result.get('remaining_domain'),
        source_identity=result.get('identity'),initial_energy_saved_raw=result.get('initial_global_weighted_energy_J'),
        final_energy_saved_raw=result.get('weighted_energy_J'))
    aggregates = list(result.get('aggregation_attempts',[]))
    if isinstance(result.get('aggregation'),dict): aggregates.append(result['aggregation'])
    for update in result.get('global_updates',[]):
        stamp = update.get('committed_at_s'); energy = update.get('weighted_energy_J')
        matched = next((a for a in aggregates if a.get('weighted_energy_J') == energy
            and a.get('completed_at_elapsed_s') == stamp and _saved_safe(a,instance,fixed,limit)),None)
        if matched is None or not _timely(stamp,limit):
            out['receipt_errors'].append({'kind':'GLOBAL_UPDATE_NOT_MATCHING_TIMELY_SAFE','stamp':stamp}); continue
        sources = update.get('scene_sources') or {}
        out['updates'].append({'committed_at_s':stamp,'energy_J':energy,
            'safe_upper_bound_J':update.get('safe_upper_bound_J'),'scene_sources':sources,
            'source':'initial_constructor' if sources and all(s == 'initial_constructor' for s in sources.values()) else 'inner_MILP'})
    out['updates'].sort(key=lambda row:row['committed_at_s'])
    initial = result.get('initial_global_weighted_energy_J')
    initial_updates = [u for u in out['updates'] if u['source'] == 'initial_constructor' and u['energy_J'] == initial]
    if initial_updates:
        out.update(initial_energy_J=initial,initial_U_J=str(_interval(initial)[1]),
                   initial_complete_at_s=initial_updates[0]['committed_at_s'])
    aggregate = result.get('aggregation')
    if (result.get('state') == 'SAFE' and result.get('rankable_energy') is True
            and _saved_safe(aggregate,instance,fixed,limit)
            and result.get('weighted_energy_J') == aggregate.get('weighted_energy_J')
            and result.get('safe_candidate') == aggregate.get('safe_candidate')):
        out.update(final_energy_J=aggregate['weighted_energy_J'],final_U_J=aggregate['safe_upper_bound_J'])
    elif result.get('safe_upper_bound_J') is not None:
        out['receipt_errors'].append({'kind':'FINAL_SAVED_U_NOT_MATCHING_TIMELY_SAFE'})
    out.update(interval_comparison(out['initial_energy_J'],out['final_energy_J']))
    out['first_SAFE_at_s'] = min((u['committed_at_s'] for u in out['updates']),default=None)
    out['first_strict_improvement_at_s'] = first_strict_time(out['initial_energy_J'],out['updates'])
    for key,receipt in (result.get('deployment_bounds') or {}).items():
        if (key in ('L0','L_a') and receipt and receipt.get('solver_reported') is False
                and receipt.get('input_sha256') == out['full_input_sha256']
                and _timely(receipt.get('formed_at_s'),limit)):
            out['independent_bounds'][key] = receipt
    initial_references = []
    for sid,scene in result.get('scenes',{}).items():
        witness = (scene.get('initialisation') or {}).get('witness') or {}
        initial_hash = _candidate_hash(witness.get('candidate'))
        initial_references.append(initial_hash is not None)
        for evaluation in scene.get('model_view_evaluations',[]):
            if evaluation.get('source') == 'initial_constructor': continue
            candidate_hash = _candidate_hash(evaluation.get('candidate'))
            physical = evaluation.get('evaluation') or {}
            out['decoded_candidate_changes'].append({'scene_id':sid,'source':evaluation.get('source'),
                'candidate_sha256':candidate_hash,'initial_candidate_sha256':initial_hash,
                'different_from_initial_decoded_candidate':None if initial_hash is None else candidate_hash != initial_hash,
                'received_at_s':evaluation.get('received_at_s'),'state':physical.get('state'),
                'complete':physical.get('complete'),'rankable_energy':physical.get('rankable_energy'),
                'completed_at_elapsed_s':physical.get('completed_at_elapsed_s')})
    out['requests'] = _request_records(invocation,result,limit)
    changed = any(row['different_from_initial_decoded_candidate'] is True
        and _timely(row.get('received_at_s'),limit) for row in out['decoded_candidate_changes'])
    out['candidate_outcome'] = ('CERTIFIED_STRICT_IMPROVEMENT' if out['strict_improvement_certified'] is True else
        'DIFFERENT_DECODED_CANDIDATE_WITHOUT_CERTIFIED_STRICT_IMPROVEMENT' if changed else
        'NO_COMPLETE_INITIAL_CANDIDATE_REFERENCE' if not initial_references or not all(initial_references) else
        'NO_DIFFERENT_DECODED_CANDIDATE_OBSERVED')
    out['different_native_vector_in_budget'] = any(r.get('different_native_vector_observed_in_budget') for r in out['requests'])
    out['actual_CutMaxIterations'] = sorted({r['native_options']['CutMaxIterations'] for r in out['requests']
        if isinstance(r.get('native_options'),dict) and 'CutMaxIterations' in r['native_options']})
    out['native_errors'] = [{'scene_id':r['scene_id'],'request_number':r.get('request_number'),
        'identifier':r.get('error_identifier'),'message':r.get('error_message')} for r in out['requests']
        if r.get('error_identifier') or r.get('error_message')]
    out['feedback_records'] = sum(len((s.get('solver_result') or {}).get('feedback',[])) for s in result.get('scenes',{}).values())
    return out


def _pair_checks(left,right):
    scenes = sorted({r['scene_id'] for call in (left,right) for r in call['requests']})
    comparisons = []
    for sid in scenes:
        a = next((r for r in left['requests'] if r['scene_id'] == sid),None)
        b = next((r for r in right['requests'] if r['scene_id'] == sid),None)
        fp_a,fp_b = (a or {}).get('model_fingerprint'),(b or {}).get('model_fingerprint')
        comparisons.append({'scene_id':sid,'scope':'first published request only; later feedback models listed separately',
            'model_fingerprint_observed':bool(fp_a and fp_b),
            'model_fingerprint_equal':None if not fp_a or not fp_b else fp_a['sha256'] == fp_b['sha256'],
            'model_component_equal':{} if not fp_a or not fp_b else {
                key:fp_a['component_sha256'][key] == fp_b['component_sha256'][key] for key in MODEL_FIELDS},
            'options':compare_options((a or {}).get('native_options'),(b or {}).get('native_options'))})
    return {'same_full_input_sha256':left.get('full_input_sha256') == right.get('full_input_sha256') if left.get('full_input_sha256') else None,
            'same_config_sha256':left.get('config_sha256') == right.get('config_sha256') if left.get('config_sha256') else None,
            'same_shared_deployment':left.get('shared_deployment') == right.get('shared_deployment'),
            'first_requests_by_scene':comparisons,
            'later_feedback_requests':{str(call['cut_max_iterations_declared']):[
                r for r in call['requests'] if r.get('round',1)>1] for call in (left,right)}}


def _plot(out,calls):
    import matplotlib
    matplotlib.use('Agg',force=True)
    import matplotlib.pyplot as plt
    fig,axes = plt.subplots(1,2,figsize=(11,4.1),sharey=True,layout='constrained')
    for ax,call in zip(axes,calls):
        limit = call.get('budget_s',300); elapsed = (call.get('timing') or {}).get('method_elapsed_s',0)
        end = min(limit,max(0.,float(elapsed))); updates = [u for u in call['updates'] if u['committed_at_s'] <= end]
        if end < limit:
            ax.axvspan(end,limit,color='#888888',alpha=.12,label='Unused budget')
            ax.axvline(end,color='#777777',linestyle='-.',linewidth=.9)
        if updates:
            xs = [u['committed_at_s'] for u in updates]; ys = [float(_interval(u['energy_J'])[1]) for u in updates]
            ax.step(xs+[end],ys+[ys[-1]],where='post',color='#1764a0',label='Saved SAFE U(t)',linewidth=1.7)
            ax.scatter(xs,ys,s=20,color='#1764a0',zorder=4)
        else: ax.text(.5,.6,'No complete SAFE U',transform=ax.transAxes,ha='center')
        for key,color,style in [('L0','#555555',':'),('L_a','#2d854b','--')]:
            receipt = call['independent_bounds'].get(key)
            if receipt and receipt['formed_at_s'] <= end:
                ax.plot([receipt['formed_at_s'],end],[float(_q(receipt['lower_bound_J']))]*2,
                    color=color,linestyle=style,linewidth=1.5,label='Independent '+key)
        if call.get('initial_energy_J') and call.get('initial_complete_at_s',limit) <= end:
            ax.plot([call['initial_complete_at_s'],end],[float(_interval(call['initial_energy_J'])[1])]*2,
                    color='#bc6c19',linestyle=(0,(5,3)),linewidth=1.1,label='Own complete init upper')
        ax.set(title='CutMaxIterations = '+str(call['cut_max_iterations_declared']),
               xlabel='Elapsed method time (s)',xlim=(0,limit))
        ax.grid(alpha=.22); handles,_ = ax.get_legend_handles_labels()
        if handles: ax.legend(fontsize=8,loc='best')
    axes[0].set_ylabel('Energy (J)')
    fig.suptitle('One fixed shared deployment; independent fresh 300 s method budgets',fontsize=11)
    fig.savefig(out/'pair_bounds.png',dpi=220); fig.savefig(out/'pair_bounds.pdf'); plt.close(fig)


def _fmt(value):
    return '—' if value is None else format(float(_q(value)),'.9g')


def summarize(pair_dir,out_dir):
    """Read only the finished pair and write a new, non-overwriting analysis."""
    pair,out = Path(pair_dir).resolve(),Path(out_dir).resolve()
    if out.exists(): raise FileExistsError(out)
    if pair == out or pair.is_relative_to(out): raise ValueError('Output cannot contain pair input')
    declaration,run = _read(pair/'declaration.json'),_read(pair/'run_record.json')
    recorded = {row['cut_max_iterations']:row for row in run.get('calls',[])}
    if any(row.get('state') in ('RUNNING','PROCESSING','STARTING') for row in recorded.values()):
        raise ValueError('Pair has an unfinished call')
    calls = []
    for value in (10,1):
        record = recorded.get(value,{})
        folder = (pair/record.get('relative_path','call_'+str(value))).resolve(); folder.relative_to(pair)
        calls.append(_call(folder,value,record))
    comparisons = _pair_checks(*calls)
    report = {'analysis_scope':ANALYSIS_SCOPE,'declaration':declaration,'run_record':run,
        'calls':calls,'posthoc_pair_checks':comparisons,
        'postprocessor_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'internal_gap_convention':'R2023b relativegap=100*(U-L)/(|U|+1); raw solver-reported values only',
        'bound_scope':'L0 original full input; L_a fixed H=a; neither is a solver-reported internal bound',
        'limitations':['one fresh call per setting, one fixed shared deployment; no overall win-rate claim',
            'no K116 result is used as a control, seed, reference energy or cache',
            'matrix fingerprints compare published arrays, not prove mathematical-domain equivalence',
            'native wall phases can overlap Python callback checks; do not sum them as disjoint CPU costs',
            'observed feedback is not an ablation or proof of feedback benefit'],
        'outputs':['calls.csv','pair_bounds.png','pair_bounds.pdf','summary.json','summary.md']}
    rows = []
    for call in calls:
        rows.append({'cut_max_iterations':call['cut_max_iterations_declared'],'state':call['state'],'reason':call['reason'],
            'initial_energy_J':call.get('initial_energy_J'),'initial_complete_at_s':call.get('initial_complete_at_s'),
            'final_energy_J':call.get('final_energy_J'),'final_U_J':call.get('final_U_J'),
            'upper_bound_improved':call.get('upper_bound_improved'),'strict_improvement_certified':call.get('strict_improvement_certified'),
            'first_SAFE_at_s':call.get('first_SAFE_at_s'),'first_strict_improvement_at_s':call.get('first_strict_improvement_at_s'),
            'candidate_outcome':call.get('candidate_outcome'),'different_native_vector_in_budget':call.get('different_native_vector_in_budget'),
            'actual_CutMaxIterations':call.get('actual_CutMaxIterations'),
            'method_elapsed_s':(call.get('timing') or {}).get('method_elapsed_s'),
            'cleanup_s':(call.get('timing') or {}).get('cleanup_s'),
            'deadline_overshoot_s':(call.get('timing') or {}).get('deadline_overshoot_s'),
            'wrapper_state':call['run_record'].get('state'),'wrapper_error':call['run_record'].get('error'),
            'source_unchanged':call['run_record'].get('source_unchanged'),
            'native_request_count':len(call['requests']),'feedback_records':call.get('feedback_records'),
            'native_errors':call.get('native_errors'),'receipt_errors':call['receipt_errors']})
    out.mkdir(parents=True,exist_ok=False)
    with (out/'calls.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=list(rows[0])); writer.writeheader()
        for row in rows: writer.writerow({key:json.dumps(value,ensure_ascii=False,separators=(',',':'))
            if isinstance(value,(dict,list)) else '' if value is None else value for key,value in row.items()})
    _plot(out,calls)
    strict_settings = [call['cut_max_iterations_declared'] for call in calls if call.get('strict_improvement_certified') is True]
    if strict_settings:
        lead = 'Cut='+str(strict_settings)+' 的本次已保存最终U严格低于各自完整初始化的能量下端；单次配对不证明设置普遍更优。'
    elif any(call.get('final_energy_J') is None or call.get('initial_energy_J') is None for call in calls):
        lead = '档案未提供两次调用各自完整的初始及最终SAFE能量，节能比较保留未决。'
    else:
        lead = '两设置均未证实相对各自完整初始化的严格节能改善。'
    if any(call.get('native_errors') or call['run_record'].get('error') or call.get('error') for call in calls):
        lead += ' 调用存在技术故障，已保存SAFE与技术状态分列。'
    lines = [lead,'','仅报告固定共享部署H=a；严格改善按各自完整初始化下端比较，不能把较小求解器目标当作真实节能。','',
        '| CutMaxIterations | 状态 / 原因 | 完整初始能量（J） | 最终U（J） | 本次严格改善 | 首SAFE / 首严格改善（s） | 方法 / 清理（s） |',
        '|---:|---|---|---:|---|---|---|']
    for call in calls:
        interval = call.get('initial_energy_J'); timing = call.get('timing') or {}
        energy = '—' if interval is None else '['+_fmt(interval[0])+', '+_fmt(interval[1])+']'
        lines.append(f"| {call['cut_max_iterations_declared']} | {call['state']} / {call['reason']} | {energy} | {_fmt(call.get('final_U_J'))} | {call.get('strict_improvement_certified')} | {call.get('first_SAFE_at_s')} / {call.get('first_strict_improvement_at_s')} | {timing.get('method_elapsed_s')} / {timing.get('cleanup_s')} |")
    lines += ['', '初始化收益、后续MILP上界下降和区间严格分离在CSV/JSON中分列。无SAFE时不填能量；曲线仅用已保存、预算内完整SAFE聚合，止于实际方法停止时刻。','']
    for call in calls:
        lines.append(f"Cut={call['cut_max_iterations_declared']}：{call.get('candidate_outcome')}；预算内不同于x0的原生向量：{call.get('different_native_vector_in_budget')}；实际原生设置：{call.get('actual_CutMaxIterations')}。")
        for error in call.get('native_errors',[]):
            lines += [f"原生错误：`{error['identifier']}`。",'```text',error.get('message') or '', '```']
    lines += ['', '首请求事后对照（反馈后的模型另列，不混为首模型）：','',
        '| 场景 | 数组指纹相等 | 其余选项原始相等 | 排除预算派生MaxTime后的其余设置相等 |',
        '|---|---|---|---|']
    for row in comparisons['first_requests_by_scene']:
        options = row['options']
        lines.append(f"| {row['scene_id']} | {row['model_fingerprint_equal']} | {options['all_other_options_equal_raw']} | {options['other_settings_equal_excluding_budget_MaxTime']} |")
    lines += ['', '逐请求phase、rootLP/内部界、节点、原始gap、x0/事件向量比较和全部选项差异见summary.json。R2023b原生relativegap按100(U−L)/(|U|+1)保留；独立L0/La与物理能耗区间分开。',
        '仅此固定H=a的两次诊断，不代表16部署搜索；K116不作control。未复算热、LP或求解；未从预算外raw结果补U。单次配对不推断总体胜率，反馈记录不证明反馈收益。']
    (out/'summary.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (out/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',required=True,type=Path)
    parser.add_argument('--out',required=True,type=Path)
    args = parser.parse_args()
    result = summarize(args.run,args.out)
    print(json.dumps({'out':str(args.out.resolve()),'analysis_scope':result['analysis_scope']},ensure_ascii=False))
