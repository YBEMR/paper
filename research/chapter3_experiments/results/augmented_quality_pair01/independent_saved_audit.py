"""K135 independent saved-byte/receipt audit; never builds, solves or heats."""
from fractions import Fraction as F
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = next(p for p in ROOT.parents if (p/'AGENTS.md').is_file() and (p/'RESEARCH_BRIEF.md').is_file())

def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def digest(v):
    return hashlib.sha256(json.dumps(v, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def save(p, value):
    Path(p).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')

def admission():
    d, ledger = read(ROOT/'declaration.json'), read(ROOT/'ledger.json')
    sources = d['source_sha256']
    assert len(sources) == 144
    assert all(sha(REPO/p) == h == sha(ROOT/'source_snapshot'/p) for p,h in sources.items())
    assert sha(ROOT/'wrapper_checks.json') == d['wrapper_checks_sha256']
    assert sha(ROOT/'method_checks.json') == d['method_checks_sha256']
    assert read(ROOT/'wrapper_checks.json')['passed'] is True
    assert read(ROOT/'wrapper_checks.json')['tests_run'] == 19
    assert read(ROOT/'method_checks.json')['passed'] is True
    assert read(ROOT/'method_checks.json')['count'] == 60
    assert all(sha(ROOT/p) == h for p,h in d['input_file_sha256'].items())
    assert digest(read(ROOT/'input_instance.json')) == d['input_sha256']
    assert digest(read(ROOT/'input_config.json')) == d['config_sha256']
    instance = read(ROOT/'input_instance.json')
    assert F(instance['window_ms']) == 400 and F(instance['start_grid_ms']) == 5
    assert [s['application_pair'] for s in instance['scenarios']] == [['A','B'], ['A','C']]
    assert all(len(s['stage_instances']) == 6 and len(s['requests']) == 2 for s in instance['scenarios'])
    assert all(all(F(x) == 50 for x in s['entry']['temperature_degC']) and
        all(F(x) == 80 for x in s['maximum_temperature_degC']) for s in instance['scenarios'])
    assert d['per_method_budget_s'] == 300 and d['scene_slice_s'] == 60
    assert d['method_call_limit'] == 2 and d['retry_allowed'] is False and d['extend_budget_allowed'] is False
    assert [j['id'] for j in d['jobs']] == ['old_n1', 'augmented_all_opp_start']
    report = {'scope': 'independent stored-byte/rule audit; no model/solver/thermal work',
        'source_current_and_snapshot_count':len(sources), 'all_source_hashes_match':True,
        'wrapper_checks':19, 'inherited_method_checks':60, 'input_hashes_match':True,
        'original_AB_AC_full_chains':True, 'window_ms':400, 'start_grid_ms':5,
        'entry_degC':50, 'maximum_degC':80, 'consumed_at_audit':ledger['consumed'],
        'per_method_budget_s':300, 'scene_cap_cooperative_s':60,
        'research_call_cap':2, 'retry_or_extension':False}
    save(ROOT/'independent_admission_audit.json', report)
    return report

def matrix_identity(p):
    import numpy as np
    result = {}
    for key in ('A','Aeq'):
        m = p[key].tocsc(copy=True)
        m.sort_indices()
        h = hashlib.sha256()
        for a in (np.asarray(m.shape,dtype='<i8'), m.indptr.astype('<i8'),
                  m.indices.astype('<i8'), m.data.astype('<f8')):
            h.update(a.tobytes())
        result[key] = {'shape':list(m.shape), 'nnz':int(m.nnz),'canonical_sha256':h.hexdigest()}
    for key in ('c','b','beq','lb','ub','intcon'):
        a = np.asarray(p[key],dtype='<i8' if key=='intcon' else '<f8').reshape(-1)
        result[key] = {'length':len(a),'sha256':hashlib.sha256(a.tobytes()).hexdigest()}
    return result

def residuals(p, x):
    import numpy as np
    x = np.asarray(x,dtype=float).reshape(-1)
    assert x.size == len(p['c']) and np.isfinite(x).all()
    integer = np.asarray(p['intcon'],dtype=int)
    values = {'inequality':float(max(0.,np.max(p['A']@x-p['b'],initial=0.))),
        'equality':float(np.max(np.abs(p['Aeq']@x-p['beq']),initial=0.)),
        'bounds':float(max(0.,np.max(p['lb']-x,initial=0.),np.max(x-p['ub'],initial=0.))),
        'integer':float(np.max(np.abs(x[integer]-np.rint(x[integer])),initial=0.)),
        'objective':float(p['c']@x)}
    values['accepted'] = all(values[k] <= 1e-9 for k in ('inequality','equality','bounds')) and values['integer'] <= 1e-6
    return values

def audit_augmented(result, folder):
    import numpy as np
    from scipy.io import loadmat
    result_rows = []
    summary = result['augmented_transport']
    for request in summary['requests']:
        mapping_path = Path(request['mapping_path'])
        mapping = read(mapping_path)
        identities = read(Path(request['identities_path']))
        names = {e['file'].split('.event_')[0] for e in request['events']}
        assert len(names) == 1
        name = names.pop()
        prefix = folder/'matlab'/name
        mat = loadmat(str(prefix.with_suffix('.mat')))
        augmented = {k:(mat[k].tocsc() if k in ('A','Aeq') else np.asarray(mat[k]).reshape(-1))
                     for k in ('A','Aeq','c','b','beq','lb','ub','intcon')}
        augmented['intcon'] = augmented['intcon'].astype(int)-1
        n, e = mapping['original_n'], mapping['original_eq_rows']
        original = {k:np.copy(augmented[k][:n]) for k in ('c','lb','ub')}
        original.update(intcon=np.copy(augmented['intcon']),
            beq=np.copy(augmented['beq'][:e]),Aeq=augmented['Aeq'][:e,:n].tocsc(),
            b=np.copy(augmented['b']),A=augmented['A'][:,:n].tolil())
        for row,col,M in zip(mapping['physical_rows'],mapping['physical_gate_columns'],mapping['physical_gate_coefficients']):
            original['A'][row,col] = M
            original['b'][row] += M
        original['A'] = original['A'].tocsc()
        assert matrix_identity(augmented) == identities['augmented']
        assert matrix_identity(original) == identities['original']
        vectors = [('initial',mat['x0'])]
        for event in request['events']:
            value = read(folder/'matlab'/event['file'])
            if value.get('x') is not None and np.asarray(value['x']).size:
                vectors.append(('callback:'+str(event['number']),value['x']))
        native = read(prefix.with_suffix('.response.json'))
        if native.get('x') is not None and np.asarray(native['x']).size:
            vectors.append(('final',native['x']))
        checked = []
        for source,x in vectors:
            x = np.asarray(x,dtype=float).reshape(-1)
            a,o = residuals(augmented,x),residuals(original,x[:n])
            checked.append({'source':source,'augmented':a,'original':o,
                'passes_declared_numeric_tolerances':a['accepted'] and o['accepted'],
                'same_as_sent_initial':bool(np.array_equal(x,np.asarray(mat['x0']).reshape(-1)))})
        actual = native['phase_seconds']['intlinprog_call']
        cap = native['solver_max_time_s_used']
        result_rows.append({'request':name,'original_n':n,'augmented_n':mapping['augmented_n'],
            'rewritten_rows':mapping['physical_rows_rewritten'],
            'retained_nonexact_physical_rows':len(mapping.get('exact_row_selection',{}).get('retained_nonrepresentable_physical_rows',[])),
            'all_16_matrix_identity_fields_match':True,'numeric_vectors':checked,
            'native_status':native['status'],'native_exitflag':native['exitflag'],
            'MaxTime_s':cap,'actual_intlinprog_call_s':actual,
            'stop_delay_over_setting_s':max(0.,actual-cap),
            'callback_publications_complete':request['callback_publications_complete'],
            'expected_callback_numbers':request['expected_callback_numbers'],
            'checked_callback_numbers':request['checked_callback_numbers'],
            'latched_unresolved':request['latched_unresolved']})
    return result_rows

def final_audit():
    d, ledger = read(ROOT/'declaration.json'),read(ROOT/'ledger.json')
    assert ledger['state'] in ('COMPLETED','BLOCKED') and 1 <= ledger['consumed'] <= 2
    assert all(sha(REPO/p) == h == sha(ROOT/'source_snapshot'/p) for p,h in d['source_sha256'].items())
    reference = REPO/'research/chapter3_experiments/results/night_k127_run02/analysis01/analysis_script.py'
    spec = importlib.util.spec_from_file_location('independent_saved_safe_checks',reference)
    prior = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prior)
    # The imported file contains saved-JSON/Fraction checks only and has a
    # guarded main. It imports no production planner/evaluator modules.
    calls = []
    results = []
    for row in ledger['calls']:
        folder = ROOT/row['id']
        result,instance = read(folder/'result.json'),read(folder/'input_instance.json')
        assert digest(instance) == d['input_sha256']
        energy = prior.full_safe(result['aggregation'],result['safe_candidate'],instance,300,'n1',result)
        accepted = []
        for candidate,receipt,source in prior.full_evaluations(result,'n1'):
            if receipt.get('state') == 'SAFE':
                prior.full_safe(receipt,candidate,instance,300,'n1',result)
                accepted.append({'candidate_sha256':digest(candidate),'source':source,
                    'formed_at_s':receipt['completed_at_elapsed_s'],
                    'energy_J':receipt['weighted_energy_J']})
        assert all(0 <= u['committed_at_s'] < 300 for u in result['global_updates'])
        closed = read(folder/'matlab/closed.json')
        assert closed['observed_tree_verified_terminated'] is True
        assert all(i['state']=='EXITED' for i in closed['process_tree_verification']['identities'])
        seed = result['condition']['seed_candidate']
        assert all(s['unit'] == next(v['unit'] for v in seed['scenes'][sid] if v['stage_id']==s['stage_id'])
            for sid,stages in result['safe_candidate']['scenes'].items() for s in stages)
        results.append(result)
        numeric = []
        if row['method']!='n1':
            try:
                numeric = audit_augmented(result,folder)
            except Exception as error:
                numeric = [{'audit_unresolved':True,'reason':f'{type(error).__name__}: {error}',
                    'scope':'missing/invalid saved native arrays; not a new physical evaluation'}]
        native_times = []
        for path in sorted((folder/'matlab').glob('request_*.response.json')):
            value = read(path)
            events = [read(p) for p in sorted(path.parent.glob(path.name.split('.')[0]+'.event_*.json'))]
            root_events = [e['values'] for e in events if e.get('kind')=='callback'
                and e.get('values',{}).get('phase')=='rootlp']
            actual,cap = value['phase_seconds']['intlinprog_call'],value['solver_max_time_s_used']
            native_times.append({'request':path.name.split('.')[0], 'exitflag':value['exitflag'],
                'actual_call_s':actual,'MaxTime_used_s':cap,
                'stop_delay_over_setting_s':max(0.,actual-cap),
                'rootlp_events_native_clock':root_events,'output_solver_reported_only':value['output']})
        calls.append({'id':row['id'],'ledger_state':row['state'],'technical_state':result['technical_state'],
            'reason':result['reason'],'complete_SAFE_receipt_verified':True,
            'energy_J':[str(v) for v in energy],'initial_energy_J':result['initial_global_weighted_energy_J'],
            'seed_sha256':digest(seed),'first_safe_s':result['first_safe_at_s'],
            'all_saved_SAFE_receipts_verified':len(accepted),'saved_SAFE_receipts':accepted,
            'distinct_full_SAFE_candidates':len({r['candidate_sha256'] for r in accepted}),
            'timing':result['timing'],'cleanup_s':closed['cleanup_wall_seconds'],
            'observed_identity_count':len(closed['process_tree_verification']['identities']),
            'all_owned_observed_identities_exited':True,'fixed_units_retained':True,
            'global_optimality_proved':result['independently_proven_optimal'],
            'global_infeasibility_proved':result['independently_proven_infeasible'],
            'native_times_and_solver_reported_outputs':native_times,
            'independent_bounds_and_gaps':result['independent_gaps'],
            'native_matrix_objectives_are_single_scene_not_system_U':True,
            'augmented_numeric_audit':numeric})
    comparison = None
    if len(results) == 2:
        old,new = calls
        comparison = {'same_fresh_seed':old['seed_sha256']==new['seed_sha256'],
            'same_initial_energy':old['initial_energy_J']==new['initial_energy_J'],
            'strict_new_SAFE_upper_below_old_lower':F(new['energy_J'][1])<F(old['energy_J'][0]),
            'old_upper_J':old['energy_J'][1],'new_upper_J':new['energy_J'][1]}
    report = {'scope':'independent saved-JSON/arrays audit; no thermal recomputation, model or solver',
        'source_current_and_snapshot_hashes_match':len(d['source_sha256']),
        'reused_saved_receipt_checker':{'path':reference.relative_to(REPO).as_posix(),'sha256':sha(reference)},
        'consumed_calls':ledger['consumed'],'ledger_state':ledger['state'],
        'calls':calls,'comparison':comparison}
    save(ROOT/'independent_final_audit.json',report)
    print(json.dumps({'consumed':ledger['consumed'],'comparison':comparison},ensure_ascii=False,indent=2))
    return report

if __name__ == '__main__':
    import sys
    if '--final' in sys.argv:
        final_audit()
    else:
        print(json.dumps(admission(), ensure_ascii=False, indent=2))
