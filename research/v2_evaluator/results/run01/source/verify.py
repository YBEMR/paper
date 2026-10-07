"""Basic sustained-safety verifier. No expected answers, box search or optimizer."""
from decimal import Decimal
from fractions import Fraction as F
import itertools
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'v1_evaluator'))
import evaluate as v1
from interval import Budget as V1Budget, Exhausted


class Budget(V1Budget):
    def __init__(self, seconds=30, fragment_limit=10000, hook=None):
        super().__init__(seconds=seconds)
        self.fragment_limit = fragment_limit
        self.fragments = 0
        self.hook = hook

    def checkpoint(self, name):
        if self.hook:
            self.hook(name)
        self.check()


def require(ok, reason):
    if not ok:
        raise v1.Invalid(reason)


def span(p):
    return max(F(s['offset_us'])+F(s['duration_us']) for s in p['stages'])


def exact_numbers(x):
    if isinstance(x, float):
        raise v1.Invalid('float_input_not_exact')
    if isinstance(x, Decimal) and not x.is_finite():
        raise v1.Invalid('nonfinite_input')
    if isinstance(x, dict):
        for v in x.values():
            exact_numbers(v)
    elif isinstance(x, (list, tuple)):
        for v in x:
            exact_numbers(v)


def rational_copy(x):
    if isinstance(x, Decimal):
        return F(x)
    if isinstance(x, dict):
        return {k:rational_copy(v) for k,v in x.items()}
    if isinstance(x, list):
        return [rational_copy(v) for v in x]
    return x


def domain_info(c):
    p = c['platform']
    domains = {}
    for u, d in p['units'].items():
        domains.setdefault(d['frequency_domain'], []).append(u)
    def fv(u, o):
        op = p['opps'][u][o]
        return F(op['f_Hz']), F(op['V'])
    possible = {u:set() for u in p['units']}
    for members in domains.values():
        pairs = set()
        for entry in c['initial_states']:
            current = {fv(u, entry['held_opps'][u]) for u in members}
            require(len(current)==1, 'initial_shared_domain_conflict')
            pairs.update(current)
        for plan in c['fixed_plans'].values():
            pairs.update(fv(s['unit'],s['opp']) for s in plan['stages'] if s['unit'] in members)
        for pair in pairs:
            for u in members:
                matches = [o for o in p['opps'][u] if fv(u,o)==pair]
                require(len(matches)==1, 'domain_OPP_mapping_not_unique_or_missing')
                possible[u].add(matches[0])
    return domains, possible


def validate(c, semantics):
    exact_numbers(c); exact_numbers(semantics)
    flags = {'relative_schedule':'T1 whole-round translation', 'extra_preparation_us':0,
             'on_switch':'stop old future releases; drain already released work; first new release equals request time',
             'same_time_priority':'finish work, then switch request, then release according to new mode; suppress old-mode same-time release',
             'opps':'set at actual Stage start only when its domain is idle; hold last OPP in idle',
             'intervals':'half-open', 'nonpreemptive':True, 'cross_round_overlap':False,
             'temperature_continuity':True, 'initial_switch_clock_origin_us':0,
             'initial_state_reset':'only at start of independent trace, never at internal switch'}
    require(all(semantics[k]==v for k,v in flags.items()), 'unsupported_execution_semantics')
    p, plans = c['platform'], c['fixed_plans']
    require(bool(plans) and bool(c['initial_states']), 'empty_plans_or_initial_set')
    v1.validate_platform(rational_copy(p))
    v1.validate_plans(rational_copy({'semantics':semantics,'platform':p,'fixed_plans':plans}))
    edges = semantics['allowed_transitions']
    require(all(len(e)==2 and e[0] in plans and e[1] in plans and e[0]!=e[1] for e in edges), 'transition_identity')
    require(len({tuple(e) for e in edges})==len(edges), 'duplicate_transition')
    for s in c['initial_states']:
        require(s['actual_mode'] in plans, 'initial_mode')
        require(s['pending_switch'] is None and s['unfinished_work']==[], 'unsupported_initial_pending_work')
        require(all(s[k]==0 for k in ['phase_us','next_release_us','mode_request_age_us','saturated_switch_age_us']), 'unsupported_initial_clock')
        require(s['instant']=='before release at t=0; no old work', 'initial_event_side')
        require(set(s['held_opps'])==set(p['units']) and all(o in p['opps'][u] for u,o in s['held_opps'].items()), 'initial_OPP')
        require(len(s['temperature_box_C'])==len(p['nodes']), 'initial_temperature_dimension')
        require(all(len(v)==2 and p['valid_temperature_C'][0]<=v[0]<=v[1]<=p['valid_temperature_C'][1] for v in s['temperature_box_C']), 'initial_temperature_range')
    return domain_info(c)


def deadline_certificate(c, semantics, budget):
    plans = c['fixed_plans']; spans = {}
    for m,p in plans.items():
        budget.check(); spans[m]=span(p)
    own = {m:F(p['relative_deadline_us'])-spans[m] for m,p in plans.items()}
    edges = [{'from':a,'to':b,'slack_us':F(plans[b]['relative_deadline_us'])-spans[a]-spans[b]} for a,b in semantics['allowed_transitions']]
    budget.checkpoint('deadline_ready')
    return dict(status='pass' if all(v>=0 for v in own.values()) and all(e['slack_us']>=0 for e in edges) else 'not_proved',
                spans_us=spans, own_slack_us=own, edge_checks=edges,
                proof='initial empty; T1 and Z0; D<=P<=L; induction across all real admissible switch times and unbounded repetitions')


def fragment_options(c, possible):
    choices = []
    units = list(c['platform']['units'])
    for u in units:
        rows = [s for p in c['fixed_plans'].values() for s in p['stages'] if s['unit']==u]
        choices.append([(o,q) for o in sorted(possible[u])
                        for q in sorted({F(0)} | {F(s['activity_increment_W']) for s in rows if s['opp']==o})])
    return units, choices


def boundary_net(c, temperatures, fragment):
    p=c['platform']; t=list(map(F,temperatures)); answer=[]
    for k,node in enumerate(p['nodes']):
        u=next(u for u,d in p['units'].items() if d['node']==node)
        opp,q=fragment[u]; o=p['opps'][u][opp]
        power=F(o['base_W'])+q+F(o['leak_W_per_K'])*(t[k]-F(p['leak_reference_C']))
        answer.append(power-sum(F(g)*(tj-F(p['ambient_C'])) for g,tj in zip(p['G_W_per_K'][k],t)))
    return answer


def thermal_certificate(c, possible, budget):
    p=c['platform']; box=c['certificate_box_C']
    require(len(box)==len(p['nodes']) and all(len(v)==2 and v[0]<=v[1] for v in box), 'malformed_certificate_box')
    inside = all(p['valid_temperature_C'][0]<=lo<=hi<=min(limit,p['valid_temperature_C'][1]) for (lo,hi),limit in zip(box,p['temperature_limit_C']))
    initial = all(all(lo<=a<=b<=hi for (a,b),(lo,hi) in zip(s['temperature_box_C'],box)) for s in c['initial_states'])
    if not inside or not initial:
        return dict(status='not_proved', reason='box_outside_valid_safe_range_or_missing_initial_coverage',initial_contained=initial,coverage_complete=False)
    units,choices=fragment_options(c,possible)
    submitted={}
    for f in c['fragment_superset']:
        budget.check()
        require(set(f['held_opps'])==set(units) and set(f['activity_W'])==set(units), 'fragment_units')
        key=tuple((f['held_opps'][u],F(f['activity_W'][u])) for u in units)
        require(all(o in p['opps'][u] and q>=0 for u,(o,q) in zip(units,key)), 'fragment_values')
        submitted[key]=f
        if len(submitted)>budget.fragment_limit:
            raise Exhausted('fragment_storage_limit')
    lo,hi=zip(*box); logs=[]; missing=[]; expected_count=0
    for key in itertools.product(*choices):
        budget.check(); expected_count+=1
        if expected_count>budget.fragment_limit:
            raise Exhausted('fragment_coverage_limit')
        if key not in submitted:
            missing.append(key)
    if missing:
        return dict(status='not_proved', reason='fragment_coverage_missing',missing=missing,coverage_complete=False,expected_count=expected_count)
    # Checking extra (unreachable) combinations is conservative, not an expansion of legal actions.
    for key in submitted:
        budget.fragments+=1; budget.checkpoint('fragment')
        f=dict(zip(units,key)); a,b=boundary_net(c,lo,f),boundary_net(c,hi,f)
        logs.append(dict(fragment=submitted[key],lower_net_W=a,upper_net_W=b,pass_faces=all(q>=0 for q in a) and all(q<=0 for q in b)))
    budget.checkpoint('thermal_certificate_ready')
    return dict(status='pass' if all(r['pass_faces'] for r in logs) else 'not_proved',initial_contained=True,coverage_complete=True,
                expected_count=expected_count,checked_count=len(logs),box_C=box,fragments=logs,
                minimum_lower_net_W=[min(v) for v in zip(*(r['lower_net_W'] for r in logs))],
                maximum_upper_net_W=[max(v) for v in zip(*(r['upper_net_W'] for r in logs))],
                proof='cooperative affine flow; positive C; exact rational face signs for complete fragment superset; T continuous at events')


def witness_trace(c, semantics):
    entry=c['initial_states'][0]
    initial=c.get('thermal_witness',{}).get('initial_temperature_C',[v[0] for v in entry['temperature_box_C']])
    require(len(initial)==len(entry['temperature_box_C']) and all(lo<=t<=hi for t,(lo,hi) in zip(initial,entry['temperature_box_C'])), 'witness_not_in_initial_set')
    requests=c.get('witness_requests',[])
    mode=entry['actual_mode']; last=F(0)
    for r in requests:
        require([mode,r['to_mode']] in semantics['allowed_transitions'], 'witness_illegal_transition')
        require(F(r['time_us'])>last and F(r['time_us'])-last>=F(c['fixed_plans'][mode]['minimum_switch_interval_us']), 'witness_illegal_switch_time')
        last=F(r['time_us']); mode=r['to_mode']
    # A valid W1 tail for replay only; sustained proof has no evaluation window.
    plan=c['fixed_plans'][mode]; d=F(plan['relative_deadline_us']); period=F(plan['period_us'])
    need=max(last+max(F(p['relative_deadline_us']) for p in c['fixed_plans'].values()),F(c.get('thermal_witness',{}).get('time_us',0)))
    k=max(0,-((-(need-last-d))//period))
    window=last+k*period+d
    return dict(id=c['id']+'_witness',initial_mode=entry['actual_mode'],initial_release_us=0,
                initial_temperature_C=initial,initial_opps=entry['held_opps'],initial_unfinished_work=[],switch_requests=requests,window_us=window)


def replay(c, semantics, budget, commit=None):
    try:
        tr=witness_trace(c,semantics)
        x=dict(platform=c['platform'],fixed_plans=c['fixed_plans'],semantics=semantics)
        rows,requests,releases,failure=v1.expand(x,tr,budget)
        budget.checkpoint('witness_schedule_ready')
        result=dict(trace=tr,schedule=rows,requests=requests,releases=releases,real_violation=False)
        if failure:
            result.update(real_violation=True,kind='deadline',failure=failure)
            if commit:
                commit(result)
            return result
        segments=v1.power_segments(x,tr,rows,F(tr['window_us']),budget)
        accuracy=dict(temperature_enclosure_width_C=Decimal('0.000001'),energy_enclosure_width_J=Decimal('0.00000001'))
        r=v1.thermal(c['platform'],tr['initial_temperature_C'],segments,accuracy,budget)
        result.update(thermal=r,real_violation=bool(r.get('known_violations')),kind='thermal' if r.get('known_violations') else 'no_verified_violation')
        if commit:
            commit(result)  # V1 retains only witnesses established before its budget boundary.
        budget.checkpoint('witness_thermal_ready')
        return result
    except (v1.Invalid,KeyError,ValueError,TypeError) as exc:
        return dict(real_violation=False,kind='invalid_witness',reason=str(exc))


def classify_point_interval(lower, upper, limit):
    require(F(lower)<=F(upper), 'reversed_interval')
    return 'violation' if F(lower)>F(limit) else 'safe_point_only' if F(upper)<=F(limit) else 'unresolved'


def verify(c, semantics, budget=None):
    budget=budget or Budget()
    out=dict(id=c.get('id'),status='unresolved',input_status='unchecked',scope='declared initial set; all admissible real-time switches and arbitrary dwell',
             coverage='incomplete',refined_layer='not_implemented',budget_status='within_limit',deadline={},thermal_certificate={},witness=None)
    phase='input'
    def commit_witness(w):
        out['witness']=w
        if w['real_violation']:
            out['status']='violation'
    try:
        budget.checkpoint('start')
        _,possible=validate(c,semantics)
        out['input_status']='valid'; phase='proof'
        budget.checkpoint('input_validated')
        out['deadline']=deadline_certificate(c,semantics,budget)
        out['thermal_certificate']=thermal_certificate(c,possible,budget)
        if c.get('witness_requests') or c.get('thermal_witness'):
            out['witness']=replay(c,semantics,budget,commit_witness)
            if out['witness']['real_violation']:
                out['status']='violation'
            budget.checkpoint('witness_committed')
        budget.checkpoint('before_final')
        if out['status']=='violation':
            out['coverage']='counterexample_sufficient'
        elif out['deadline']['status']=='pass' and out['thermal_certificate']['status']=='pass':
            out.update(status='sustained_safe',coverage='all_declared_processes_certified')
        else:
            out.update(status='unresolved',coverage='sufficient_certificate_not_established')
    except Exhausted as exc:
        out.update(budget_status='exhausted',coverage='incomplete',reason=str(exc))
    except (MemoryError,ArithmeticError) as exc:
        out.update(coverage='incomplete',reason=f'{type(exc).__name__}: {exc}',numerical_or_resource_status='unresolved')
    except (v1.Invalid,KeyError,TypeError,ValueError) as exc:
        out.update(reason=str(exc),coverage='incomplete')
        if phase=='input':
            out.update(status='input_invalid',input_status='invalid')
        else:
            out['certificate_status']='invalid_or_unsupported'
    out['diagnostic']=dict(elapsed_s=time.monotonic()-budget.start,fragments=budget.fragments,panels=budget.panels,peak_refinements=budget.refinements)
    return out
