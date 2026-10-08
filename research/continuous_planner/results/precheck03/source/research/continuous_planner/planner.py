"""CP1 bounded continuous candidate prototype. Not a complete time-domain solver.

Production functions accept only problem/analysis/protocol/runtime, never probes.
Integer structures are queried by MILP; all exported offsets are reconstructed
and validated using rational arithmetic, independent of solver feasibility flags.
"""
from copy import deepcopy
from decimal import Decimal
from fractions import Fraction as F
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DRAFT = HERE.parent / 'continuous_planner_precheck_draft'
sys.path.insert(0, str(HERE.parent / 'joint_evaluator'))
import evaluate_joint as joint


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'), parse_float=Decimal)


def save(p, x):
    with Path(p).open('x', encoding='utf-8') as f:
        json.dump(x, f, ensure_ascii=False, indent=2, default=joint.v1.encode)
        f.write('\n')


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def identities():
    files = list(HERE.glob('*.py')) + list(HERE.glob('*.m'))
    files += [DRAFT / n for n in ['inputs.json', 'expected.json', 'check_static.py',
                                 'DEPENDENCIES_SHA256.json', 'SHA256SUMS.txt']]
    files += list(joint.sources().values())
    return {str(p.relative_to(REPO)): sha(p) for p in files}


class Clock:
    def __init__(self, seconds):
        self.start = time.monotonic()
        self.seconds = float(seconds)

    def elapsed(self):
        return time.monotonic() - self.start

    def remaining(self):
        return max(0., self.seconds - self.elapsed())

    def check(self):
        if not self.remaining():
            raise TimeoutError('total_wall_budget')


class Matlab:
    def __init__(self, folder, clock):
        self.folder = Path(folder); self.folder.mkdir(parents=True, exist_ok=False)
        self.clock = clock; self.index = 0
        self.log = (self.folder / 'matlab.log').open('w', encoding='utf-8')
        prefs = REPO / '.runtime/matlab_prefs'; prefs.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, MATLAB_PREFDIR=str(prefs))
        exe = Path('F:/Matlab2023/Program_Files/MATLAB_R2023b/bin/matlab.exe')
        script = "addpath('%s'); worker('%s');" % (HERE.as_posix().replace("'", "''"), self.folder.resolve().as_posix().replace("'", "''"))
        self.process = subprocess.Popen([str(exe), '-batch', script], env=env,
            stdout=self.log, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            self.wait(self.folder / 'ready.json')
            self.info = read(self.folder / 'ready.json')
            if not self.info['license'] or not self.info['solver']:
                raise RuntimeError('Optimization Toolbox unavailable')
        except BaseException:
            self.close(); raise

    def wait(self, path):
        while not path.exists():
            self.clock.check()
            if self.process.poll() is not None:
                raise RuntimeError('MATLAB worker exited; inspect matlab.log')
            time.sleep(.01)

    def solve(self, model, cap):
        self.clock.check(); self.index += 1
        payload = model.payload(min(float(cap), self.clock.remaining()))
        p = self.folder / ('request_%04d.json' % self.index)
        tmp = p.with_suffix('.tmp'); save(tmp, payload); tmp.rename(p)
        out = self.folder / ('response_%04d.json' % self.index)
        self.wait(out)
        result = read(out)
        # Read/transfer work is charged; no late integer candidate is accepted.
        self.clock.check()
        if result['state'] != 'returned':
            raise RuntimeError(result.get('message', 'solver error'))
        return result

    def close(self):
        (self.folder / 'stop').touch(exist_ok=True)
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # This is this task's own process; never kill unrelated MATLAB jobs.
            self.process.terminate()
            try: self.process.wait(timeout=5)
            except subprocess.TimeoutExpired: self.process.kill()
        self.log.close()


def counts(problem):
    out = {m: F(0) for m in problem['modes']}
    ev = problem['evaluation']
    for path, weight in zip(ev['paths'], ev['weights']):
        tr = path['trace']; mode = tr['initial_mode']; start = F(tr['initial_release_us'])
        for switch in tr['switch_requests'] + [{'time_us': tr['window_us'], 'to_mode': None}]:
            stop = F(switch['time_us']); period = F(problem['modes'][mode]['period_us'])
            # Same-time old release suppressed; window-end release excluded.
            out[mode] += F(weight) * max(0, math.ceil((stop - start) / period))
            start, mode = stop, switch['to_mode']
    return out


def lower_bound(problem):
    # Nonnegative baseline/leakage; complete declared U1 work. Scope CP1.
    weights = counts(problem)
    return sum(weights[m] * sum(min(F(o['duration_us'])*F(o['activity_increment_W'])/1000000
                for o in st['options']) for st in mode['stages'])
               for m, mode in problem['modes'].items())


def conflict(platform, a, b):
    ua, ub = a['unit'], b['unit']
    if ua == ub: return True
    if platform['units'][ua]['frequency_domain'] != platform['units'][ub]['frequency_domain']:
        return False
    x, y = platform['opps'][ua][a['opp']], platform['opps'][ub][b['opp']]
    return (x['f_Hz'], x['V']) != (y['f_Hz'], y['V'])


class Model:
    def __init__(self, problem):
        self.problem = problem; self.f=[]; self.lb=[]; self.ub=[]; self.integer=[]
        self.A=[]; self.b=[]; self.Aeq=[]; self.beq=[]
        self.x={}; self.a={}; self.pairs=[]
        weights = counts(problem)
        for m, mode in problem['modes'].items():
            for st in mode['stages']:
                for o in st['options']:
                    self.x[m,st['id'],o['option_id']] = self.var(0,1,True,
                        weights[m]*F(o['duration_us'])*F(o['activity_increment_W'])/1000)
                self.a[m,st['id']] = self.var(0,F(mode['relative_deadline_us'])/1000)
        for m, mode in problem['modes'].items():
            deadline=F(mode['relative_deadline_us'])/1000
            for st in mode['stages']:
                i=st['id']
                self.row({self.x[m,i,o['option_id']]:1 for o in st['options']},1,True)
                self.row(self.end(m,i),deadline)
                for pre in st['predecessors']:
                    self.row(self.add(self.end(m,pre),{self.a[m,i]:-1}),0)
            for si,sj in itertools.combinations(mode['stages'],2):
                i,j=si['id'],sj['id']
                for oi,oj in itertools.product(si['options'],sj['options']):
                    if not conflict(problem['platform'],oi,oj): continue
                    xi,xj=self.x[m,i,oi['option_id']],self.x[m,j,oj['option_id']]
                    z=self.var(0,1,True)
                    self.pairs.append((m,i,j,oi['option_id'],oj['option_id'],z))
                    self.row(self.add(self.end(m,i),{self.a[m,j]:-1,xi:deadline,xj:deadline,z:deadline}),3*deadline)
                    self.row(self.add(self.end(m,j),{self.a[m,i]:-1,xi:deadline,xj:deadline,z:-deadline}),2*deadline)

    def var(self,lo,hi,integer=False,cost=0):
        k=len(self.f); self.f.append(F(cost)); self.lb.append(F(lo)); self.ub.append(F(hi))
        if integer: self.integer.append(k)
        return k

    @staticmethod
    def add(*rows):
        out={}
        for row in rows:
            for k,v in row.items(): out[k]=out.get(k,F(0))+F(v)
        return out

    def row(self,row,rhs,eq=False):
        (self.Aeq if eq else self.A).append({k:F(v) for k,v in row.items()})
        (self.beq if eq else self.b).append(F(rhs))

    def end(self,m,i):
        st=next(s for s in self.problem['modes'][m]['stages'] if s['id']==i)
        return {self.a[m,i]:F(1)} | {self.x[m,i,o['option_id']]:F(o['duration_us'])/1000 for o in st['options']}

    def payload(self,seconds):
        def trip(rows): return [[r+1,k+1,float(v)] for r,row in enumerate(rows) for k,v in row.items() if v]
        return dict(A=trip(self.A),b=list(map(float,self.b)),Aeq=trip(self.Aeq),beq=list(map(float,self.beq)),
            rows=len(self.A),eqrows=len(self.Aeq),n=len(self.f),f=list(map(float,self.f)),
            lb=list(map(float,self.lb)),ub=list(map(float,self.ub)),integer=[i+1 for i in self.integer],seconds=seconds)

    def decode(self,values,tolerance):
        if len(values)!=len(self.f): raise ValueError('solver_vector_length')
        bits={}
        for k in self.integer:
            v=F(values[k]); nearest=round(v)
            if nearest not in (0,1) or abs(v-nearest)>F(tolerance): raise ValueError('noninteger_or_out_of_bounds')
            bits[k]=nearest
        chosen={m:{} for m in self.problem['modes']}; literals=[]
        for m,mode in self.problem['modes'].items():
            for st in mode['stages']:
                opts=[o for o in st['options'] if bits[self.x[m,st['id'],o['option_id']]]]
                if len(opts)!=1: raise ValueError('nonunique_selected_option')
                chosen[m][st['id']]=opts[0]['option_id']
                literals.append((self.x[m,st['id'],opts[0]['option_id']],1))
        dirs={m:[] for m in chosen}
        for m,i,j,oi,oj,z in self.pairs:
            if chosen[m][i]==oi and chosen[m][j]==oj:
                dirs[m].append([i,j] if bits[z] else [j,i]); literals.append((z,bits[z]))
        signature=joint.digest({'chosen':chosen,'directions':dirs})
        return dict(chosen=chosen,directions=dirs,signature=signature,literals=literals)

    def exclude_query(self,structure):
        literals=structure['literals']; zeros=sum(v==0 for k,v in literals)
        self.row({k:1 if v else -1 for k,v in literals},len(literals)-1-zeros)


def selected(problem,structure,m):
    return {st['id']:next(o for o in st['options'] if o['option_id']==structure['chosen'][m][st['id']])
            for st in problem['modes'][m]['stages']}


def representatives(problem,structure):
    tables=[{}, {}, {}]
    for m,mode in problem['modes'].items():
        rows=selected(problem,structure,m); d={i:F(o['duration_us']) for i,o in rows.items()}
        edges={(p,s['id']) for s in mode['stages'] for p in s['predecessors']}
        edges |= {tuple(e) for e in structure['directions'][m]}
        order=[]; pending=set(rows)
        while pending:
            ready=sorted(i for i in pending if not any(a in pending for a,b in edges if b==i))
            if not ready: raise ValueError('exact_direction_cycle')
            order.extend(ready); pending.difference_update(ready)
        early={}; late={}; D=F(mode['relative_deadline_us'])
        for i in order: early[i]=max([F(0)]+[early[a]+d[a] for a,b in edges if b==i])
        if any(early[i]+d[i]>D for i in rows): raise ValueError('exact_earliest_deadline')
        for i in reversed(order): late[i]=min([D-d[i]]+[late[b]-d[i] for a,b in edges if a==i])
        for tab,offsets in zip(tables,[early,{i:(early[i]+late[i])/2 for i in rows},late]): tab[m]=offsets
    out=[]; seen=set()
    for label,table in zip(['all_E','all_M','all_L'],tables):
        if not legal(problem,structure,table): raise ValueError('exact_reconstruction_illegal')
        key=joint.digest(table)
        if key not in seen: out.append((label,table)); seen.add(key)
    return out


def legal(problem,structure,table):
    # Independent of solver variables and big-M inequalities.
    for m,mode in problem['modes'].items():
        rows=selected(problem,structure,m); t=table[m]
        end={i:F(t[i])+F(o['duration_us']) for i,o in rows.items()}
        if any(t[i]<0 or end[i]>mode['relative_deadline_us'] for i in rows): return False
        if any(end[p]>t[s['id']] for s in mode['stages'] for p in s['predecessors']): return False
        if any(end[a]>t[b] for a,b in structure['directions'][m]): return False
        for i,j in itertools.combinations(rows,2):
            if conflict(problem['platform'],rows[i],rows[j]) and max(t[i],t[j])<min(end[i],end[j]): return False
    return True


def bundle(problem,analysis,structure,table):
    if not legal(problem,structure,table): raise ValueError('illegal_candidate')
    plans={}
    for m,mode in problem['modes'].items():
        plans[m]={k:deepcopy(v) for k,v in mode.items() if k!='stages'}; stages=[]
        rows=selected(problem,structure,m)
        for st in mode['stages']:
            o=rows[st['id']]
            stages.append(dict(id=st['id'],predecessors=deepcopy(st['predecessors']),
                offset_us=table[m][st['id']],**{k:deepcopy(o[k]) for k in ['unit','opp','duration_us','activity_increment_W']}))
        plans[m]['stages']=stages
    return dict(id='CP1_'+joint.digest({'chosen':structure['chosen'],'table':table})[:16],
        candidate=dict(platform=deepcopy(problem['platform']),fixed_plans=plans,semantics=deepcopy(problem['semantics'])),
        safety=dict(initial_states=deepcopy(problem['initial_states']),**{k:deepcopy(analysis[k]) for k in
            ['certificate_box_C','fragment_superset','witness_requests']}),evaluation=deepcopy(problem['evaluation']))


def compare(a,b):
    return 'a_strictly_lower' if F(a[1])<F(b[0]) else 'b_strictly_lower' if F(b[1])<F(a[0]) else 'overlap_or_tie'


class Evaluations:
    def __init__(self): self.cache={}; self.hits=0

    def evaluate(self,b,clock,cap,hook=None):
        clock.check(); key=joint.digest(joint.binding(b))
        if key in self.cache:
            self.hits+=1; r=deepcopy(self.cache[key]); clock.check(); return r
        budget=joint.v2.Budget(seconds=min(float(cap),clock.remaining()),hook=hook)
        # Align the inner deadline with the outer absolute deadline (creation
        # overhead must not accidentally give the evaluator extra time).
        budget.seconds=min(budget.seconds, max(0.,clock.start+clock.seconds-budget.start))
        r=joint.evaluate_bundle(b,budget)
        # A committed violation survives a late transfer, but never late energy.
        if clock.remaining()<=0:
            status='candidate_violation' if r['status']=='candidate_violation' else 'unresolved'
            kept={}
            if status=='candidate_violation':
                safety=r.get('sustained_safety') or (r.get('safety_receipt') or {}).get('result',{})
                if safety.get('witness',{}).get('real_violation'):
                    kept['witness']=deepcopy(safety['witness'])
                    # A violated finite path may still carry prefix energy in
                    # diagnostics; transfer only the actual violation evidence.
                    if 'thermal' in kept['witness']:
                        kept['witness']['thermal']={'known_violations':kept['witness']['thermal'].get('known_violations',[])}
                kept['finite_path_violation_receipts']=deepcopy(r.get('path_violation_receipts',{}))
                if r.get('finite_path_energy'):
                    for tid,tr in r['finite_path_energy'].get('traces',{}).items():
                        if tr.get('execution_status')=='deadline_violation':
                            kept.setdefault('finite_deadlines',{})[tid]=deepcopy(tr.get('failure'))
            r=dict(status=status,budget_status='exhausted',certified_candidate_energy={'status':'unavailable'},
                   committed_evidence=kept,reason='outer_return_after_budget')
        # Do not cache a timeout as a completed assessment.
        if r.get('budget_status')=='within_limit' and r['status'] in ['certified_candidate','candidate_violation']:
            self.cache[key]=deepcopy(r)
        return r


def search(problem,analysis,protocol,runtime,folder,clock,backend):
    clock.check()
    if protocol['representative_sequence']!=['all_E','all_M','all_L'] or protocol['mixed_representatives']:
        raise ValueError('unsupported_protocol')
    L0=lower_bound(problem); model=Model(problem); evaluator=Evaluations(); seen=set()
    result=dict(L0_J=L0,U_J=None,best_candidate=None,structures=[],events=[],
        optimality='unproved',infeasibility='unproved',coverage='unsearched_continuous_times_and_structures',
        stop=None,source_scope='CP1 diagnostic; finite representative search')
    try:
        for index in range(int(runtime['max_structures'])):
            clock.check()
            rec=dict(index=index,state='querying',representatives=[]); result['structures'].append(rec)
            query_start=clock.elapsed(); sol=backend.solve(model,runtime['per_query_seconds'])
            rec['query_seconds']=clock.elapsed()-query_start
            rec['solver_reported']={k:sol.get(k) for k in ['fval','exitflag','output','solve_s']}
            rec['bound_scope']='remaining MILP query domain, mJ activity proxy; not original certified lower bound'
            if not sol.get('x'):
                rec['state']='no_integer_candidate'; result['stop']='solver_no_new_structure_or_unresolved'; break
            structure=model.decode(sol['x'],runtime['integer_decode_tolerance'])
            if structure['signature'] in seen: raise ValueError('duplicate_signature_after_no_good')
            rec['structure']=structure; rec['state']='processing'; seen.add(structure['signature'])
            try: reps=representatives(problem,structure)
            except ValueError as exc:
                rec.update(state='exact_no_heat_rejection',reason=str(exc)); model.exclude_query(structure); continue
            for label,table in reps:
                clock.check(); start=clock.elapsed(); b=bundle(problem,analysis,structure,table)
                r=evaluator.evaluate(b,clock,runtime['per_evaluation_seconds'])
                entry=dict(label=label,table_us=table,bundle=b,result=r,finished_s=clock.elapsed(),seconds=clock.elapsed()-start)
                rec['representatives'].append(entry)
                objective=r.get('certified_candidate_energy',{})
                if objective.get('status')=='available' and clock.remaining()>0:
                    high=F(objective['energy_J'][1])
                    if result['U_J'] is None or high<result['U_J']:
                        result['U_J']=high; result['best_candidate']=b['id']
                        result['events'].append(dict(t_s=clock.elapsed(),U_J=high,candidate=b['id']))
                clock.check()
            rec['state']='representatives_complete_other_times_unsearched'
            model.exclude_query(structure)
            if result['U_J'] is not None and result['U_J']==L0:
                result.update(optimality='certified_by_original_L0',stop='trusted_bound_closure'); break
        if result['stop'] is None: result['stop']='structure_limit'
    except TimeoutError as exc: result['stop']='budget_exhausted'; result['reason']=str(exc)
    except (MemoryError,RuntimeError,ValueError,ArithmeticError) as exc:
        result['stop']='resource_or_interface_unresolved'; result['reason']=str(exc)
    result['elapsed_s']=clock.elapsed(); result['cache_hits']=evaluator.hits
    # Serialize after search, separately from the decision budget.
    save(Path(folder)/'search.json',result)
    return result
