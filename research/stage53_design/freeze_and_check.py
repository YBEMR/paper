"""53: one-time input freeze and static algebra audit; NO scheduler or thermal simulation.

Run from any directory. Existing frozen outputs are never overwritten.
This is artifact-generation/checking code, not an experimental entry point.
"""
from pathlib import Path
from fractions import Fraction as F
import hashlib
import json
import math
import platform
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(name, value):
    with (OUT / name).open('x', encoding='utf-8', newline='\n') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def run():
    outputs = ['protected_before.json', 'inputs_v1.json', 'rules_v1.json',
               'freeze_manifest.json', 'static_checks_v1.json']
    if any((OUT / x).exists() for x in outputs):
        raise RuntimeError('Frozen output exists; no overwrite. Read the existing manifest/checks.')

    protected = set()
    for dirname in ['matlab_config_value_src', 'matlab_thermal_sched_src',
                    'coordination43_design', 'prefix46_design']:
        protected.update(p for p in (ROOT / 'research' / dirname).rglob('*') if p.is_file())
    protected.update(p for p in (ROOT / 'research').glob('*.md')
                     if p.name[:2].isdigit() and 1 <= int(p.name[:2]) <= 52)
    before = {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(protected)}
    write_new('protected_before.json', before)

    graph_path = ROOT / 'research/evidence_20260925/band51/stage_graph_static.json'
    graph = json.loads(graph_path.read_text(encoding='utf-8-sig'))
    stages = []
    generators = []
    cpu_modes = []
    for i, (ref_ms, alpha, ops) in enumerate([
        (1, 1, [0, 0]), (2, 0.5, [1, 65]),
        (2, 1, [66, 265]), (1, 0.25, [266, 266])
    ]):
        sid = f'S{i}'
        stages.append(dict(stage_type=sid, operators_inclusive=ops,
                           predecessors=[] if i == 0 else [f'S{i-1}'],
                           allowed_units=['C1', 'C2', 'N'] if i == 1 else ['C1', 'C2']))
        generators.append(dict(stage_type=sid, reference_duration_s=ref_ms / 1000,
                               alpha=alpha, u_W=1, v_W=1))
        for unit in ['C1', 'C2']:
            for mode, ratio in [('L', 0.5), ('H', 1)]:
                cpu_modes.append(dict(stage_type=sid, unit_id=unit, frequency_id=mode,
                                      duration_s=ref_ms / 1000 * (1-alpha+alpha/ratio),
                                      active_increment_W=1+ratio**2))
    packs = []
    for pid, power in [('P_low', 1), ('P_high', 4), ('P_tie', 3.75)]:
        packs.append(dict(package_id=pid, evidence_level='L3',
                          generation='synthetic; generated CPU modes, stipulated NPU mode',
                          modes=cpu_modes + [dict(stage_type='S1', unit_id='N', frequency_id='FIXED',
                                                  duration_s=0.001, active_increment_W=power)]))
    cases = []
    for pid in ['P_low', 'P_high']:
        for d_ms in [6, 10]:
            for label, temp in [('cold', 30), ('hot', 78)]:
                cases.append(dict(case_id=f'{pid}_D{d_ms}_{label}', cohort='main', package_id=pid,
                                  requests=[dict(request_id=r, release_s=0, deadline_s=d_ms/1000,
                                                 stage_types=['S0','S1','S2','S3']) for r in ['A','B']],
                                  initial_C=[temp,temp]))
    for cid, pid, d_ms in [('check_stage_energy_tie','P_tie',10),
                           ('check_noheat_infeasible','P_low',4)]:
        cases.append(dict(case_id=cid, cohort='check', package_id=pid,
                          requests=[dict(request_id=r, release_s=0, deadline_s=d_ms/1000,
                                         stage_types=['S0','S1','S2','S3']) for r in ['A','B']],
                          initial_C=[30,30]))
    data = dict(
        schema_version='stage53-v1', evidence_level='L3',
        status='frozen input, not executed; structural provenance is not numeric calibration',
        model=dict(model_id='lite-model_efficientdet_lite0_int8_1.tflite',
                   sha256=graph['model_sha256'], git_blob=graph['git_blob'],
                   partition_source='https://github.com/mrsnu/band/pull/226',
                   commit='5af78b1644f77069b5f128bcc14f896cc65d8f5f',
                   graph_source='research/evidence_20260925/band51/stage_graph_static.json',
                   operator_count=267, input_shape=[1,320,320,3], input_type='UINT8'),
        stage_types=stages,
        units=[dict(unit_id='C1',kind='CPU',resource_set=['abstract_cpu_slot_1'],frequency_domain='D0'),
               dict(unit_id='C2',kind='CPU',resource_set=['abstract_cpu_slot_2'],frequency_domain='D0'),
               dict(unit_id='N',kind='NPU',resource_set=['abstract_npu_slot'],frequency_domain=None)],
        cpu_frequencies=[dict(frequency_id='L',ratio_to_reference=0.5),
                         dict(frequency_id='H',ratio_to_reference=1)],
        cpu_response=dict(duration_formula='d_ref*((1-alpha)+alpha/x)',
                          increment_formula='u+v*x^2',parameters=generators),
        system=dict(window_s=0.020,start_grid_s=0.001,idle_cpu_total_W=0.2,
                    idle_npu_W=0.3,external_W=0.5,
                    extra_transfer_duration_s=0,extra_transfer_energy_J=0,
                    extra_switch_duration_s=0,extra_switch_energy_J=0),
        thermal=dict(node_order=['CPU_aggregate','NPU'],capacity_J_per_K=[0.0025,0.0025],
                     env_conductance_W_per_K=[0.05,0.05],coupling_W_per_K=0.025,
                     ambient_C=25,limit_C=[80,80],external_power_outside_thermal_boundary=True),
        packages=packs,cases=cases,
        provenance=[
            dict(fields=['model','stage_types.operators_inclusive','stage_types.predecessors'],
                 attribute='file_fact_and_local_static_derivation',source='51号 / stage_graph_static.json'),
            dict(fields=['stage_types.allowed_units'],attribute='author_report_plus_L3_expansion',
                 source='PR226 reported CPU/NPU category support; C1/C2 expansion is a research assumption'),
            dict(fields=['units','cpu_frequencies','cpu_response','packages','cases','system.window_s','system.start_grid_s'],
                 attribute='L3_synthetic_or_formula_derived',source='user-approved 53 plan; not fitted from operator count'),
            dict(fields=['system.idle_cpu_total_W','system.idle_npu_W','system.external_W','thermal'],
                 attribute='L3_explicit_reuse',source='43/46 abstract network and power accounting; not hardware calibration'),
            dict(fields=['system.extra_transfer_duration_s','system.extra_transfer_energy_J',
                         'system.extra_switch_duration_s','system.extra_switch_energy_J'],
                 attribute='L3_idealization',source='52/53 zero additional overhead boundary')])
    rules = dict(
        schema_version='stage53-rules-v1',hypothesis='H52',
        objective='min system energy on common finite window under deadline/resource/domain/thermal constraints',
        methods=['joint_noheat','one_full_suffix_per_initial_action','same_domain_thermal_reference'],
        execution=dict(known_requests=True,nonpreemptive=True,migration=False,in_stage_frequency_change=False,
                       cpu_domain='D0',cpu_overlap_requires_same_frequency=True,
                       frequency_change_only_when_domain_empty=True,npu_capacity=1,
                       execution_intervals='[start,finish)',same_time_event_order='complete then start',
                       grid_applies_to='start only; do not round durations, deadlines or finish times',
                       request_completion='finish of S3',allow_waiting=True,
                       shared_response_across_requests=True,shared_response_across_cpu_units=True),
        tolerance=dict(time_s=1e-9,energy_absolute_J=1e-10,energy_relative=1e-8,temperature_C=1e-6),
        energy_layers=dict(order='raw energy ascending',anchor='first still unassigned energy',
                           member_test='abs(E-anchor)<=max(1e-10,1e-8*max(abs(E),abs(anchor)))',
                           chaining=False),
        ordering=dict(keys=['energy_layer','sum_request_finish_s','max_request_finish_s','canonical_key'],
                      stage_order=['A.S0','A.S1','A.S2','A.S3','B.S0','B.S1','B.S2','B.S3'],
                      canonical_per_stage=['start_s','unit_id','frequency_id'],unit_order=['C1','C2','N'],
                      mode_order=['L','H','FIXED'],
                      secondary_numeric_sort='unrounded finite numeric values, ascending; time tolerance only for legality'),
        baseline=dict(initial_time_s=0,action='all actual starts at initial time, including Stage/unit/mode; empty set is wait',
                      candidate_space='all legal no-heat complete schedules over all legal mode and energy layers',
                      representatives_per_action=1,representative='minimum under ordering',
                      representative_order='same ordering',thermal_check='entire complete representative and idle tail',
                      stop='first certified safe representative',
                      all_rejected='no_safe_representative, unless unresolved/time budget prevents conclusion',
                      returned_plan='fixed full schedule, not event-by-event online replanning',
                      noheat_generation_incomplete='unresolved; partial library is not an exact planner'),
        thermal_verdict=dict(safe='every node peak < limit - band',
                             violation='any node peak > limit + band',
                             unresolved='otherwise, including equality at either band boundary',
                             evaluation='continuous constant-power segment extrema including endpoints/stationary points and tail'),
        evaluation=dict(energy='(idle_cpu_total+idle_npu+external)*window+sum(active_increment*duration)',
                        independent_check='piecewise system-power integration',
                        cpu_heat='idle_cpu_total + sum increments of all running CPU-mapped stages',
                        npu_heat='idle_npu + increment of running NPU-mapped stage',
                        external_heat='none within declared two-node boundary',
                        valid_energy_ranking='complete, resource/dependency/domain/grid/deadline legal, certified thermal safe'),
        budget=dict(seconds_per_case_per_method=60,includes=['generation','sorting','selection','thermal_evaluation'],
                    share_precomputed_library=False,read_reference_in_baseline=False,
                    timeout='retain certified witnesses/bounds and unresolved fields; never exclusion',
                    rerun_with_larger_budget=False),
        reporting=dict(main_count=8,check_count=2,cohorts_separate=True,
                       reference_evidence=['safe_witness','lower_bound_J','upper_bound_J','optimum_value_proved',
                                           'optimal_configuration_set_complete','exclusion_proved','unresolved'],
                       output_fields=['full_schedule','full_configuration','request_completion_s','energy_J',
                                      'peak_temperature_C_by_node','thermal_status','completion_status',
                                      'candidate_coverage','budget_status'],
                       symmetry='CPU label swaps are not mapping gains',
                       no_safe_representative='not a proof of infeasibility',
                       baseline_gap='safe lower-energy independent witness proves a gap lower bound, not necessarily exact optimum',
                       hot_case_outcomes='not predicted; no input changes to force failure or mapping changes'),
        parameter_changes='never overwrite v1; any correction gets a new version and reason; no result-driven tuning')

    # Inputs and rules are saved and hashed BEFORE checking numerical implications.
    write_new('inputs_v1.json', data)
    write_new('rules_v1.json', rules)
    manifest = dict(frozen_at_utc=datetime.now(timezone.utc).isoformat(),
                    phase='before static algebra checks; no scheduler/thermal trajectory executed',
                    files={x:sha(OUT/x) for x in ['inputs_v1.json','rules_v1.json','freeze_and_check.py','protected_before.json']},
                    source_graph_sha256=sha(graph_path),python=platform.python_version(),platform=platform.platform())
    write_new('freeze_manifest.json', manifest)

    checks = []
    def check(name, condition, details=None):
        checks.append(dict(name=name,passed=bool(condition),details=details))

    check('exact_operator_coverage', [op for s in stages for op in range(s['operators_inclusive'][0],s['operators_inclusive'][1]+1)] == list(range(267)))
    check('matches_51_graph', all(s['stage_type']==g['id'] and s['operators_inclusive']==g['operators_inclusive'] for s,g in zip(stages,graph['stages'])) and len(graph['stages'])==4)
    check('eight_main_two_check',sum(c['cohort']=='main' for c in cases)==8 and sum(c['cohort']=='check' for c in cases)==2)
    check('unique_cases', len({c['case_id'] for c in cases})==10)
    expected_ms = {'S0':(2,1),'S1':(3,2),'S2':(4,2),'S3':(1.25,1)}
    energies = {}
    for pack in packs:
        rows=pack['modes']
        check(pack['package_id']+'_mode_count',len(rows)==17 and len({(r['stage_type'],r['unit_id'],r['frequency_id']) for r in rows})==17)
        check(pack['package_id']+'_legal_modes',all(r['unit_id'] in stages[int(r['stage_type'][1:])]['allowed_units'] and r['duration_s']>0 and r['active_increment_W']>=0 and math.isfinite(r['duration_s']) and math.isfinite(r['active_increment_W']) for r in rows))
        for i, p in enumerate(generators):
            for mode,x in [('L',F(1,2)),('H',F(1))]:
                a=F(str(p['alpha'])); d=F(str(p['reference_duration_s']))*(1-a+a/x); q=1+x*x
                selected=[r for r in rows if r['stage_type']==f'S{i}' and r['frequency_id']==mode]
                check(f'{pack["package_id"]}_S{i}_{mode}_formula_symmetry',len(selected)==2 and all(abs(r['duration_s']-float(d))<1e-15 and abs(r['active_increment_W']-float(q))<1e-15 for r in selected))
                check(f'{pack["package_id"]}_S{i}_{mode}_expected_duration',abs(float(d)*1000-expected_ms[f'S{i}'][0 if mode=='L' else 1])<1e-12)
                energies[f'S{i}_{mode}_J']=float(d*q)
        n=next(r for r in rows if r['unit_id']=='N')
        energies[pack['package_id']+'_S1_N_J']=n['duration_s']*n['active_increment_W']
        check(pack['package_id']+'_isolated_fastest_5ms',abs(sum(min(r['duration_s'] for r in rows if r['stage_type']==f'S{i}') for i in range(4))-.005)<1e-15)
    check('S1_energy_order',energies['P_low_S1_N_J']<energies['S1_L_J']<energies['P_high_S1_N_J'] and abs(energies['P_tie_S1_N_J']-energies['S1_L_J'])<1e-15)
    check('NPU_faster_than_both_CPU_modes',.001<.002<.003)
    check('deadlines_window_and_shared_stage_parameters', all(c['requests'][0]['deadline_s']==c['requests'][1]['deadline_s'] and all(0==r['release_s']<r['deadline_s']<=.020 and r['stage_types']==['S0','S1','S2','S3'] for r in c['requests']) for c in cases))
    check('deadline_multipliers',F(6,5)==F('1.2') and F(10,5)==2)
    check('noheat_infeasible_by_chain_lower_bound',.004<.005,'lower bound only; no schedule constructed or searched')
    check('noninteger_finish_grid_rule',F(5,4)>1 and math.ceil(F(5,4))==2,'a 1.25ms duration started at 0 ends at 1.25ms; earliest successor grid point 2ms')
    cap=F('0.0025'); env=F('0.05'); coupling=F('0.025')
    gdiag=env+coupling; determinant=gdiag*gdiag-coupling*coupling
    lambdas=[env/cap,(env+2*coupling)/cap]
    idle_cpu=F('0.2'); idle_npu=F('0.3')
    idle_x=[(gdiag*idle_cpu+coupling*idle_npu)/determinant,
            (coupling*idle_cpu+gdiag*idle_npu)/determinant]
    check('passive_stable_RC',cap>0 and env>0 and coupling>=0 and determinant>0 and all(x>0 for x in lambdas))
    check('thermal_time_constants',sorted([1/x for x in lambdas])==[F('.025'),F('.05')])
    check('idle_equilibrium',idle_x==[F('4.5'),F('5.5')])
    # Scalar comparison bound for ANY legal schedule, NOT a trajectory simulation.
    # M=max(T_CPU-Ta,T_NPU-Ta), D+M <= -20*M + 4.3/0.0025.
    cold_bound=25+86+(5-86)*math.exp(-.010/.050)
    check('cold_all_legal_schedules_sufficient_bound',cold_bound<80-1e-6 and cold_bound>31,
          'until latest possible completion <=10ms use max injection 4.3W; afterwards max idle equilibrium comparison is 31C')
    check('configuration_upper_bound',4**6*5**2==102400)
    historical=json.loads((ROOT/'research/evidence_20260925/contract52/protected_before.json').read_text(encoding='utf-8-sig'))
    check('matches_prior_52_historical_hashes',all((ROOT/p).is_file() and sha(ROOT/p)==h for p,h in historical.items()))
    changed=[p for p,h in before.items() if not (ROOT/p).is_file() or sha(ROOT/p)!=h]
    check('protected_files_unchanged',not changed,changed)
    check('frozen_files_unchanged',all(sha(OUT/p)==h for p,h in manifest['files'].items()))
    result=dict(audit_type='static structure and scalar algebra only',
                input_sha256=sha(OUT/'inputs_v1.json'),rules_sha256=sha(OUT/'rules_v1.json'),
                protected_count=len(before),checks=checks,passed=sum(x['passed'] for x in checks),
                failed=sum(not x['passed'] for x in checks),stage_activity_energy_J=energies,
                RC=dict(decay_rates_per_s=[float(x) for x in lambdas],
                        time_constants_s=[float(1/x) for x in lambdas],idle_equilibrium_C=[float(25+x) for x in idle_x]),
                cold_all_legal_schedule_peak_upper_bound_C=cold_bound,
                cold_bound_scope='all complete legal schedules in these cold cases over 0..20ms; not a prediction of actual peak',
                simulations=0,schedule_searches=0,matlab_runs=0,experimental_source_edits=0,
                H52='not evaluated; hot-case feasibility and baseline quality untested')
    write_new('static_checks_v1.json',result)
    print(json.dumps({k:result[k] for k in ['protected_count','passed','failed','input_sha256','rules_sha256','cold_all_legal_schedule_peak_upper_bound_C']},ensure_ascii=False,indent=2))
    if result['failed']:
        raise RuntimeError('Static checks failed; preserve record and investigate, do not retune cases.')


if __name__ == '__main__':
    run()
