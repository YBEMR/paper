"""P1 implementations of the virtual-core first-fit and ETA-TS list schedulers."""
from bisect import bisect_left, insort
from collections import Counter
from math import exp, log
from statistics import mean
import numpy as np
from numba import njit

SW = 5
BIN = 100


class Calendar:
    """Exact tick calendar. Compatible same-OPP work can overlap on the two CPUs."""
    def __init__(self, problem):
        self.p = problem
        self.rows = [None] * problem.n
        self.units = [[] for _ in range(4)]

    def add(self, i, u, k, t):
        self.rows[i] = (u, k, int(t))
        insort(self.units[u], (t, t + self.p.dur(i, u, k), k, i))

    def remove(self, i):
        u, k, t = self.rows[i]
        self.units[u].remove((t, t + self.p.dur(i, u, k), k, i))
        self.rows[i] = None

    def slot(self, i, u, k, left, deadline):
        duration = self.p.dur(i, u, k)
        latest = min(deadline, self.p.horizon - SW * (k != 0)) - duration
        t = max(int(left), SW * (k != 0))
        related = (u, 1-u) if u < 2 else (u,)
        while t <= latest:
            after = t
            for v in related:
                entries = self.units[v]
                pos = max(0, bisect_left(entries, (t-SW,))-1)
                while pos < len(entries):
                    start, end, freq, _ = entries[pos]
                    if start >= t + duration + SW:
                        break
                    gap = SW * (freq != k)
                    if (v == u or gap) and start < t+duration+gap and t < end+gap:
                        after = max(after, end+gap)
                    pos += 1
            if after == t:
                return t
            t = after
        return None


def geometric(values):
    return exp(mean(log(x) for x in values))


class Profile:
    def __init__(self, p):
        self.energy = {}
        self.task_factor = {}
        self.order = {}
        self.mode_factor = {}
        self.thermal = {}
        self.residual = {}
        self.up = {}
        for stage in ("pre", "main", "post"):
            kinds = [k+"."+stage for k in "AB"]
            modes = sorted({(u,k) for kind,u,k in p.profile if kind == kinds[0]})
            for kind in kinds:
                for u,k in modes:
                    idle, _, busy, _ = p.exact[kind,u,k]
                    self.energy[kind,u,k] = float((busy-idle)*p.profile[kind,u,k][0]/10000)
                self.task_factor[kind] = geometric(self.energy[kind,u,k] for u,k in modes)
            for u,k in modes:
                factor = geometric(self.energy[kind,u,k]/self.task_factor[kind] for kind in kinds)
                self.mode_factor[stage,u,k] = factor
                slopes = p.idle_beta.copy()
                slopes[u] = p.idle[u,k][1]
                if u < 2:
                    slopes[1-u] = p.idle[1-u,k][1]
                resistance = np.linalg.inv(p.G-np.diag(slopes))[u,u]
                self.thermal[stage,u,k] = factor * resistance
            self.order[stage] = sorted(modes, key=lambda m:(self.mode_factor[stage,*m],m))
            self.residual[stage] = max(abs(self.task_factor[t]*self.mode_factor[stage,u,k]/self.energy[t,u,k]-1)
                                       for t in kinds for u,k in modes)
        for kind in "AB":
            rank = 0
            for stage in ("post","main","pre"):
                t = kind+"."+stage
                fastest = {u:max(k for v,k in self.order[stage] if v==u) for u,k in self.order[stage]}
                rank += mean(p.profile[t,u,k][0] for u,k in fastest.items())
                self.up[t] = rank

    def li_modes(self, stage):
        return sorted(self.order[stage], key=lambda m:(self.thermal[stage,*m],m))


@njit(cache=True)
def predict(bins, initial, cap, conductance, ambient, idle, beta, horizon):
    x = initial.copy()
    peak = np.max(x)
    for j in range(len(bins)):
        dt = min(BIN, horizon-j*BIN)/10000.
        power = idle + bins[j,:4] + (beta+bins[j,4:])*(x-35.)
        rate = (power - conductance@(x-ambient))/cap
        mid = x + .5*dt*rate
        power = idle + bins[j,:4] + (beta+bins[j,4:])*(mid-35.)
        x += dt*(power-conductance@(mid-ambient))/cap
        peak = max(peak,np.max(x))
    return peak


class HeatProbe:
    def __init__(self,p):
        self.p = p
        self.bins = np.zeros(((p.horizon+BIN-1)//BIN,8))

    def add(self,i,u,k,t,sign):
        p = self.p
        duration, watts, slope = p.profile[p.kinds[i],u,k]
        end = t+duration
        for j in range(t//BIN,(end-1)//BIN+1):
            width = min(BIN,p.horizon-j*BIN)
            fraction = sign*(min(end,(j+1)*BIN)-max(t,j*BIN))/width
            self.bins[j,u] += fraction*(watts-p.idle35[u])
            self.bins[j,u+4] += fraction*(slope-p.idle_beta[u])

    def peak(self):
        p = self.p
        return predict(self.bins,p.initial,p.cap,p.G,float(p.ta),p.idle35,p.idle_beta,p.horizon)


def earliest_ready(p, book, i):
    return p.req[i//3]["release_tick"] if i%3 == 0 else p.finish(i-1,book.rows[i-1])


def hard_limit(p,i):
    r = p.req[i//3]
    remaining = range(i+1,3*(i//3+1))
    return r["deadline_tick"]-sum(min(p.dur(j,*m) for m in p.options[j]) for j in remaining)


def order_by_rank(p,profile):
    return sorted(range(p.n),key=lambda i:(-profile.up[p.kinds[i]],p.req[i//3]["release_tick"],i))


def reference(p,profile):
    """Maximum-frequency EFT reference solely for per-request level slack."""
    book = Calendar(p)
    for i in order_by_rank(p,profile):
        if i%3 and book.rows[i-1] is None:
            continue
        start = earliest_ready(p,book,i)
        stage = p.kinds[i].split(".")[1]
        modes = profile.order[stage]
        fastest = {u:max(k for v,k in modes if v==u) for u,_ in modes}
        opts = []
        for u,k in fastest.items():
            t = book.slot(i,u,k,start,p.horizon)
            if t is not None:
                opts.append((t+p.dur(i,u,k),u,k,t))
        if not opts:
            # Reference is a bound/guide, never an initial solution. Fall back
            # to an isolated fastest chain for requests missing a reference row.
            continue
        _,u,k,t = min(opts)
        book.add(i,u,k,t)
    return subdeadlines(p,book)


def subdeadlines(p,book):
    limits=[]
    for j,request in enumerate(p.req):
        ids=range(3*j,3*j+3)
        if all(book.rows[i] is not None for i in ids):
            aft=[p.finish(i,book.rows[i]) for i in ids]
        else:
            time=request["release_tick"]
            aft=[]
            for i in ids:
                time+=min(p.dur(i,*mode) for mode in p.options[i])
                aft.append(time)
        slack=request["deadline_tick"]-aft[-1]
        limits.extend(min(request["deadline_tick"],int(a+slack*level/3)) for level,a in enumerate(aft,1))
    return limits


def zhou(p,profile,stats):
    book=Calendar(p)
    probe=HeatProbe(p)
    for level,stage in enumerate(("pre","main","post")):
        queue=sorted(range(level,p.n,3),key=lambda i:(-profile.task_factor[p.kinds[i]],p.req[i//3]["release_tick"],i))
        for u,k in profile.order[stage]:
            pending=[]
            for i in queue:
                t=book.slot(i,u,k,earliest_ready(p,book,i),hard_limit(p,i))
                if t is None:
                    stats["timing_reject"]+=1
                else:
                    probe.add(i,u,k,t,1)
                    stats["thermal_probes"]+=1
                    if probe.peak()<=80:
                        book.add(i,u,k,t)
                        continue
                    probe.add(i,u,k,t,-1)
                    stats["thermal_reject"]+=1
                pending.append(i)
            queue=pending
            if not queue:
                break
        if queue:
            stats["unplaced_in_layer"]=len(queue)
            stats["failed_stage"]=level
            return book
    return book


def li_map(p,profile,stats):
    limits=reference(p,profile)
    book=Calendar(p)
    for i in order_by_rank(p,profile):
        modes=profile.li_modes(p.kinds[i].split(".")[1])
        left=earliest_ready(p,book,i)
        fallback=[]
        for u,k in modes:
            t=book.slot(i,u,k,left,hard_limit(p,i))
            if t is None:
                continue
            end=t+p.dur(i,u,k)
            if end<=limits[i]:
                book.add(i,u,k,t)
                break
            fallback.append((end,u,k,t))
        else:
            if not fallback:
                stats["failed_task"]=i
                return book
            _,u,k,t=min(fallback)
            stats["earliest_finish_fallback"]+=1
            book.add(i,u,k,t)
    return book


def latest_finishes(p,book):
    result = [p.req[i//3]["deadline_tick"] if i%3==2 else book.rows[i+1][2] for i in range(p.n)]
    for unit in book.units:
        for (_,_,k,i),(start,_,next_k,_) in zip(unit,unit[1:]):
            result[i]=min(result[i],start-SW*(k!=next_k))
    return result


def lft(p,book,stats):
    order=sorted(range(p.n),key=lambda i:(-p.finish(i,book.rows[i]),i))
    for i in order:
        u,k,t=book.rows[i]
        if k==0:
            continue
        unit=book.units[u]
        pos=bisect_left(unit,(t,))+1
        next_start,next_k = (unit[pos][0],unit[pos][2]) if pos<len(unit) else (p.horizon,0)
        deadline = p.req[i//3]["deadline_tick"] if i%3==2 else book.rows[i+1][2]
        book.remove(i)
        accepted=False
        for mode in range(k):
            limit=min(deadline,next_start-SW*(next_k!=mode))
            duration=p.dur(i,u,mode)
            first=book.slot(i,u,mode,t,limit)
            if first is None:
                continue
            half=first+(limit-first-duration)//2
            start=book.slot(i,u,mode,half,limit)
            book.add(i,u,mode,first if start is None else start)
            stats["LFT_lowered"]+=1
            stats["LFT_delayed"]+=int(book.rows[i][2]>t)
            accepted=True
            break
        if not accepted:
            book.add(i,u,k,t)

