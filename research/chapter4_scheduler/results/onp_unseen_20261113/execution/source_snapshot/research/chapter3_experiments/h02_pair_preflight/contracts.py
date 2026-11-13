"""H02 stage A: exact finite parameter contracts, not trajectory evaluation.
No scheduling, thermal propagation, HEFT, optimizer or lower-bound imports.
"""
from fractions import Fraction as F

REFERENCE = {
    'main_baseline_sha': '20fb232a81d69782b8ebd1fc1972a6bc96fff09e',
    'protocol_head_sha': 'f63cc4f8c5ceb7161a15ce55c6cf610081482f30',
    'H03_blob': '69f9faef66b63ba100bc42ee0fb8d52cdf8848a4',
    'locations': ['protocols/H03_主线探索7受控实施与预检任务书_20261023.md §2 A5',
                  'protocols/H02R_同真值响应消融独立审查与修订附录_20261023.md §2 P1/P2',
                  'evidence/source_manifest.json'],
    'source_fields': ['config_v01.json:37-110,111-144,185-192',
                      'inputs.py:58-127,130-202,205-256',
                      'control_policy.py:35-83'],
}


def exact(value, path):
    if isinstance(value, bool) or not isinstance(value, (str, int, F)):
        raise ValueError(path + ': exact string/integer/Fraction required')
    try:
        return F(value)
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError(path + ': invalid exact scalar') from error


def require(condition, path, message):
    if not condition:
        raise ValueError(path + ': ' + message)


def encoded(value):
    if isinstance(value, F):
        return str(value)
    if isinstance(value, dict):
        return {key: encoded(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [encoded(item) for item in value]
    return value


def static_monotonicity_contract(config_H, instance_H, instance_R):
    """Check H03 A5 using only exact algebra on supplied parameter records.

    config_H is the independently copied, explicitly auto-L H config, not the
    unadapted legacy config. White-diff/support isolation belongs to views.py.
    Raises ValueError at the first failed premise, with its data path.
    A PASS verifies finite premises of P1/P2; it is never a candidate SAFE.
    """
    checks = []
    def passed(name, details):
        checks.append({'name': name, 'passed': True, 'details': encoded(details)})
    try:
        platform = config_H['platform']
        nodes = platform['node_order']
        domains = platform['domains']
        units = platform['units']
        require(nodes == ['CPU1', 'CPU2', 'GPU0', 'NPU0'], 'platform.node_order', 'four declared nodes required')
        require(set(domains) == {'CPU', 'GPU', 'NPU'}, 'platform.domains', 'CPU/GPU/NPU domains required')
        unit_map = {unit['id']: unit for unit in units}
        require(len(unit_map) == len(units) == 4, 'platform.units', 'unique four execution units required')
        require(set(unit_map) == set(nodes), 'platform.units', 'execution units must match local nodes')
        for label, instance in [('H', instance_H), ('R', instance_R)]:
            require(instance['platform'] == platform, label + '.platform', 'must equal the same H physical platform')
            require(instance['execution_rules'] == config_H['execution_rules'], label + '.execution_rules', 'control rules differ')
            require(instance['id'] in ('base__R1', 'base__R2'), label + '.id', 'only frozen base R1/R2 permitted')
            require(instance['condition_id'] == 'base', label + '.condition_id', 'must retain base identity')
            require(instance['response_variant'] == label and instance['settings']['response_variant'] == label,
                    label + '.response_variant', 'planning response tags inconsistent')
        require(instance_H['id'] == instance_R['id'], 'H/R.id', 'same problem required')
        require(config_H['defaults']['response_variant'] == 'H', 'config_H.defaults.response_variant', 'H config required')
        passed('shared_H_platform_and_frozen_case', {'problem_id': instance_H['id'], 'nodes': nodes})

        overheads = ('extra_transfer_time_ms', 'extra_switch_time_ms', 'extra_handoff_time_ms',
                     'extra_transfer_energy_J', 'extra_switch_energy_J', 'extra_handoff_energy_J')
        for label, owner in [('config_H', config_H), ('H', instance_H), ('R', instance_R)]:
            rules = owner['execution_rules']
            for key in ('preemption', 'migration', 'in_stage_opp_change'):
                require(rules[key] is False, label + '.execution_rules.' + key, 'must be false')
            require(rules['switch_only_when_domain_empty'] is True, label + '.execution_rules', 'empty-domain switching required')
            require(rules['idle_holds_last_opp'] is False and rules['idle_policy'] == 'auto_low_immediate_v1',
                    label + '.execution_rules.idle_policy', 'explicit auto-L required')
            require(exact(rules['idle_delay_ms'], label + '.idle_delay_ms') == 0, label + '.idle_delay_ms', 'must be zero')
            require(rules['interval_convention'] == '[start,end)', label + '.interval_convention', 'half-open intervals required')
            for key in overheads:
                require(exact(rules[key], label + '.' + key) == 0, label + '.' + key, 'nonzero overhead breaks contract')
        passed('auto_L_atomic_execution_and_zero_overheads', {'policy': 'auto_low_immediate_v1', 'overhead_fields': list(overheads)})

        domain_details = {}
        membership = []
        for domain_id, domain in domains.items():
            path = 'platform.domains.' + domain_id
            require(set(domain['opps']) == {'L', 'M', 'H'}, path + '.opps', 'exact L/M/H set required')
            require(domain['reference_opp'] == 'H' and domain['entry_opp'] == 'L', path, 'reference H and entry L required')
            frequencies = [exact(domain['opps'][k]['frequency_GHz'], path + '.' + k + '.frequency_GHz') for k in ('L', 'M', 'H')]
            voltages = [exact(domain['opps'][k]['voltage_V'], path + '.' + k + '.voltage_V') for k in ('L', 'M', 'H')]
            require(0 < frequencies[0] < frequencies[1] < frequencies[2], path + '.opps', 'L unique minimum and H maximum frequency required')
            require(all(v > 0 for v in voltages), path + '.opps', 'voltages must be positive')
            baseline = [exact(domain['baseline_W'][k], path + '.baseline_W.' + k) for k in ('L', 'M', 'H')]
            slopes = [exact(domain['local_temperature_slope_W_per_K'][k], path + '.lambda.' + k) for k in ('L', 'M', 'H')]
            for name, vector in [('baseline_W', baseline), ('local_temperature_slope_W_per_K', slopes)]:
                require(0 <= vector[0] <= vector[1] <= vector[2], path + '.' + name, 'must be nonnegative and nondecreasing by frequency')
            distribution = [exact(v, path + '.baseline_heat_distribution') for v in domain['baseline_heat_distribution']]
            require(len(distribution) == len(nodes) and all(v >= 0 for v in distribution) and sum(distribution) == 1,
                    path + '.baseline_heat_distribution', 'nonnegative unit-sum spatial distribution required')
            require(len(domain['unit_ids']) == len(set(domain['unit_ids'])), path + '.unit_ids', 'duplicate domain membership')
            for uid in domain['unit_ids']:
                require(uid in unit_map, path + '.unit_ids', 'unknown unit')
                unit = unit_map[uid]
                require(unit['domain_id'] == unit['power_group_id'] == domain_id, 'unit.' + uid, 'one domain power group required')
                require(unit['thermal_node_id'] == uid, 'unit.' + uid + '.thermal_node_id', 'local activity heat node required')
                require('baseline_W' not in unit, 'unit.' + uid, 'per-unit duplicated baseline not permitted')
            membership.extend(domain['unit_ids'])
            domain_details[domain_id] = {'frequency_GHz': frequencies, 'baseline_W': baseline, 'local_lambda_W_per_K': slopes,
                                          'baseline_distribution': distribution, 'reference_opp': 'H', 'entry_opp': 'L'}
        require(sorted(membership) == sorted(unit_map), 'platform.domains', 'units must belong to exactly one domain')
        cpu = domains['CPU']
        require(cpu['unit_ids'] == ['CPU1', 'CPU2'], 'CPU.unit_ids', 'shared two-unit CPU domain required')
        require([exact(v, 'CPU.distribution') for v in cpu['baseline_heat_distribution']] == [F(1,2), F(1,2), F(0), F(0)],
                'CPU.baseline_heat_distribution', 'one domain baseline split equally over its two nodes')
        cpu_once = {}
        for k in ('L', 'M', 'H'):
            total = exact(cpu['baseline_W'][k], 'CPU.baseline_W.' + k)
            allocated = [total * exact(v, 'CPU.distribution') for v in cpu['baseline_heat_distribution']]
            require(sum(allocated) == total, 'CPU.baseline_W.' + k, 'domain baseline must be charged once, not once per core')
            cpu_once[k] = {'domain_charge_W': total, 'node_allocation_W': allocated,
                           'lambda_each_CPU_node_W_per_K': exact(cpu['local_temperature_slope_W_per_K'][k], 'CPU.lambda.' + k)}
        passed('ordered_OPP_baseline_local_leakage_and_nonnegative_injection', domain_details)
        passed('CPU_domain_baseline_once_local_leakage_per_node', {'symbolic_allocation': cpu_once, 'scope': 'Static model accounting, not a schedule evaluation'})

        catalog = {stage['id']: stage for stage in config_H['stage_catalog']}
        require(len(catalog) == len(config_H['stage_catalog']), 'stage_catalog', 'duplicate Stage IDs')
        alphas = []
        for stage in catalog.values():
            for device, profile in stage['profiles'].items():
                path = stage['id'] + '.profiles.' + device
                alpha = exact(profile['alpha'], path + '.alpha')
                require(0 <= alpha <= 1, path + '.alpha', 'must be in [0,1]')
                require(exact(profile['d_ref_ms'], path + '.d_ref_ms') > 0, path + '.d_ref_ms', 'must be positive')
                require(exact(profile['q_ref_W'], path + '.q_ref_W') >= 0, path + '.q_ref_W', 'must be nonnegative')
                alphas.append(alpha)
        mode_count = 0; strict_count = 0; reference_count = 0
        for sid, h_modes in instance_H['stage_modes'].items():
            require(sid in catalog, 'stage_modes.' + sid, 'unknown catalog Stage')
            r_modes = instance_R['stage_modes'][sid]
            keyed = {}
            for label, values in [('H', h_modes), ('R', r_modes)]:
                table = {}
                for mode in values:
                    key = (mode['shared_stage_id'], mode['unit_id'], mode['opp_id'])
                    require(key not in table, label + '.stage_modes.' + sid, 'duplicate mode identity')
                    table[key] = mode
                keyed[label] = table
            require(set(keyed['H']) == set(keyed['R']), 'H/R.stage_modes.' + sid, 'mode support differs')
            for key, h in keyed['H'].items():
                r = keyed['R'][key]; uid = h['unit_id']; unit = unit_map[uid]; device = unit['device_class']
                profile = catalog[sid]['profiles'][device]; domain = domains[unit['domain_id']]; k = h['opp_id']
                path = sid + '@' + uid + ':' + k
                frequency = exact(domain['opps'][k]['frequency_GHz'], path + '.frequency')
                reference_frequency = exact(domain['opps']['H']['frequency_GHz'], path + '.reference_frequency')
                voltage = exact(domain['opps'][k]['voltage_V'], path + '.voltage')
                reference_voltage = exact(domain['opps']['H']['voltage_V'], path + '.reference_voltage')
                alpha = exact(profile['alpha'], path + '.profile_alpha')
                scale = exact(instance_H['duration_scale'][catalog[sid]['application']], path + '.scale')
                require(scale > 0, path + '.scale', 'must be positive')
                dref = exact(profile['d_ref_ms'], path + '.profile_d_ref') * scale
                dh = dref * (1-alpha+alpha*reference_frequency/frequency)
                dr = dref * reference_frequency/frequency
                power = exact(profile['q_ref_W'], path + '.q_ref') * (voltage/reference_voltage)**2 * frequency/reference_frequency
                for label, mode, expected_d, expected_a in [('H', h, dh, alpha), ('R', r, dr, F(1))]:
                    require(mode['shared_stage_id'] == sid and mode['unit_id'] == uid and mode['opp_id'] == k,
                            label + '.' + path, 'mode identity mismatch')
                    require(mode['domain_id'] == mode['power_group_id'] == unit['domain_id'] and mode['thermal_node_id'] == unit['thermal_node_id'],
                            label + '.' + path, 'domain/group/local activity injection mismatch')
                    for name, expected in [('frequency_GHz',frequency), ('voltage_V',voltage), ('d_ref_ms',dref),
                                           ('alpha',expected_a), ('duration_ms',expected_d), ('activity_power_W',power),
                                           ('activity_energy_J',power*expected_d/1000)]:
                        require(exact(mode[name], label + '.' + path + '.' + name) == expected,
                                label + '.' + path + '.' + name, 'response/power/derived-energy formula mismatch')
                require(dr >= dh, path + '.duration', 'R duration must not be shorter than H')
                if k == 'H':
                    require(dr == dh == dref, path + '.reference_duration', 'reference durations must agree')
                    reference_count += 1
                strict_count += int(dr > dh); mode_count += 1
        passed('P1_alpha_response_power_energy_and_reference_equalities', {'profile_alpha_range': [min(alphas),max(alphas)],
               'mode_count': mode_count, 'strictly_longer_R_modes': strict_count, 'equal_reference_modes': reference_count,
               'inequality': 'd_R-d_H=d_ref*(1-alpha)*(f_ref/f-1)>=0'})

        c = [exact(v, 'platform.C') for v in platform['heat_capacity_J_per_K']]
        g = [[exact(v, 'platform.G') for v in row] for row in platform['conductance_W_per_K']]
        n = len(nodes)
        require(len(c) == n and all(v > 0 for v in c), 'platform.C', 'positive diagonal capacities required')
        require(len(g) == n and all(len(row) == n for row in g), 'platform.G', 'matrix dimension mismatch')
        for i in range(n):
            require(g[i][i] > 0 and sum(g[i]) > 0, 'platform.G.row.' + nodes[i], 'positive grounded row sum required')
            for j in range(n):
                require(g[i][j] == g[j][i], 'platform.G', 'passive symmetric conductance required')
                if i != j:
                    require(g[i][j] <= 0 and -g[i][j]/c[i] >= 0, 'platform.G.' + nodes[i] + '.' + nodes[j], 'Metzler off-diagonal condition violated')
        passed('P2_positive_C_passive_grounded_G_and_Metzler', {'C_J_per_K': c, 'G_row_sums_W_per_K': [sum(row) for row in g],
               'condition': 'offdiag(-C^-1*G)>=0; no trajectory or stability experiment'})
        ambient = exact(platform['ambient_temperature_degC'], 'platform.ambient')
        reference = exact(platform['reference_temperature_degC'], 'platform.reference')
        require(ambient == reference == 25, 'platform.temperature_reference', 'ambient=reference=25 required')
        require([exact(v, 'platform.valid_range') for v in platform['power_model_temperature_range_degC']] == [F(20),F(100)],
                'platform.valid_range', '20..100 degC required')
        require(exact(platform['external_common_power_W'], 'platform.external_power') == F(3,10), 'platform.external_power', '0.30 W required')
        distribution = [exact(v, 'platform.external_heat') for v in platform['external_common_heat_distribution']]
        require(len(distribution) == n and all(v == 0 for v in distribution), 'platform.external_heat', 'external power must not heat local nodes')
        passed('P2_reference_valid_range_and_external_energy_only', {'ambient_and_reference_degC': ambient,
               'model_range_degC': [20,100], 'external_common_power_W': F(3,10), 'external_common_400ms_energy_J': F(3,25)})

        for label, instance in [('H', instance_H), ('R', instance_R)]:
            require(exact(instance['window_ms'], label+'.window_ms') == 400, label+'.window_ms', '400 ms required')
            require(exact(instance['start_grid_ms'], label+'.start_grid_ms') == 5, label+'.start_grid_ms', '5 ms required')
            require(len(instance['scenarios']) == 2, label+'.scenarios', 'exact AB and AC required')
            pairs = []
            for scene in instance['scenarios']:
                path = label + '.scenarios.' + scene['id']; pairs.append(tuple(scene['application_pair']))
                entry = scene['entry']
                temp = [exact(v, path+'.entry') for v in entry['temperature_degC']]
                limits = [exact(v, path+'.limit') for v in scene['maximum_temperature_degC']]
                require(len(temp) == len(limits) == n and all(v == 50 and v-ambient >= 0 for v in temp), path+'.entry', '50 degC and nonnegative rise required')
                require(all(v == 80 for v in limits), path+'.limits', '80 degC required')
                require(entry['unfinished_work'] == [] and entry['domain_opp'] == {d:'L' for d in domains}, path+'.entry', 'empty work and L entry required')
                require(exact(scene['weight'], path+'.weight') == F(1,2), path+'.weight', 'each scenario weight must be 1/2')
            require(sorted(pairs) == [('A','B'),('A','C')], label+'.scenarios', 'AB/AC membership required')
        require(instance_H['scenarios'] == instance_R['scenarios'], 'H/R.scenarios', 'requests, DAG, deadlines, weights or entries changed')
        require(instance_H.get('start_domain') == instance_R.get('start_domain'), 'H/R.start_domain', 'declared start domain changed')
        passed('P1_same_requests_start_domain_and_P2_same_initial_window', {'window_ms':400, 'start_grid_ms':5,
               'entry_degC':50, 'initial_rise_K':F(25), 'limits_degC':80, 'scenario_weights':[F(1,2),F(1,2)],
               'model_lower_bound_reason':'nonnegative source and positive system imply T>=Ta=25>20; upper bound requires R SAFE'})
        targets = config_H['accuracy_targets']
        for name, expected in [('temperature_enclosure_width_K',F(1,1000)), ('energy_absolute_error_J',F(1,1000000)), ('energy_relative_error',F(1,1000000))]:
            require(exact(targets[name], 'accuracy_targets.'+name) == expected, 'accuracy_targets.'+name, 'frozen target mismatch')
        for name, expected in [('allow_temperature_limit_violation',False), ('thermal_checks_continuous',True), ('unresolved_temperature_is_not_safe_or_a_reliable_exclusion',True)]:
            require(targets[name] is expected, 'accuracy_targets.'+name, 'unsafe or noncontinuous acceptance rule')
        passed('frozen_accuracy_and_no_temperature_tolerance', {'temperature_width_K':F(1,1000), 'energy_absolute_J':F(1,1000000), 'energy_relative':F(1,1000000)})
    except (KeyError, TypeError, IndexError, StopIteration, ZeroDivisionError) as error:
        raise ValueError('H02_STATIC_CONTRACT malformed parameter structure: '+str(error)) from error
    return {'passed': True, 'checks': checks,
            'P1_scope': 'Finite premises only. Fixed complete R-legal candidate, identical modes and absolute starts: H intervals are subsets. No search success/optimality claim.',
            'P2_scope': 'Finite premises of positive-RC comparison only. A complete R-SAFE trajectory implies the SAME candidate is H-safe and E_H<=E_R in the model; no new SAFE, trajectory or comparison of two searched candidates.',
            'reference': dict(REFERENCE), 'research_calls': 0, 'thermal_evaluations': 0,
            'new_safe': 0, 'formal_budget_authorized': False}
