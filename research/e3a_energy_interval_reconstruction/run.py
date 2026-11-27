"""Execute one development cell. Per-cell evidence caches are physically separate."""
import os,sys,time,resource,random,json,gzip,traceback
from shared import *
from regions import windows
from solve import local

def brief(cert):
    m=cert['metrics']
    return dict(plan=cert['plan'],J=m['E_J'],bounds=m['E_bounds'],status=m['status'],
                E35=cert['E35_J'],activity=m['activity_J'],base=m['base_J'],switch=m['switch_J'],
                temperature=m['temperature_J'],external=m['external_J'],slack_ms=m['min_deadline_slack_ms'],
                margin_C=m['safe_margin_K'])
def improves(a,b):return a['status']=='SAFE' and a['bounds'][1]<b['bounds'][0]
def logs(path):
    return [json.loads(line) for line in path.read_bytes().splitlines()]
def native_plan(path):
    from common import decode
    return decode(json.loads(gzip.decompress(path.read_bytes())))
def spent_cpu():
    r=resource.getrusage(resource.RUSAGE_CHILDREN)
    return time.process_time()+r.ru_utime+r.ru_stime
class Cell:
    def __init__(self,case,arm,started):
        import g1io
        self.case=case;self.arm=arm;self.start=started;self.folder=RUN/case/arm
        self.cap=600 if arm=='diagnostic' else 300
        self.folder.mkdir(parents=True,exist_ok=False);g1io.OUT=self.folder/'physical'
        self.out=g1io.OUT
        self.p,self.seed=load_native(case)
        self.past=0;self.n=0;self.probes={}
        self.bestplan=self.seed
        _,c=g1io.assess(self.p,self.seed);self.base=self.best=brief(c)
        assert abs(self.base['J']-read(DATA/case/'identity.json')['energy_J'])<1e-8
        scores,self.regions=windows(self.p,self.seed)
        if arm=='diagnostic':
            put(self.folder/'windows.json',scores);put(self.folder/'regions.json',self.regions)
        else:assert self.regions==read(RUN/case/'diagnostic/regions.json')
        self.record(dict(kind='initial',result=self.base))
    def age(self):return time.monotonic()-self.start
    def record(self,row):
        row.update(seq=self.n,wall_s=self.age(),cpu_s=spent_cpu());self.n+=1
        with (self.folder/'candidates.jsonl').open('a') as f:f.write(json.dumps(row,separators=(',',':'))+'\n')
    def certify(self,plan,original):
        import g1io
        from model import transitions,Invalid
        from compact import Illegal
        try:transitions(self.p,*plan)
        except Invalid as e:return dict(status='TIMING_INVALID',reason=str(e))
        key=g1io.store(self.p,plan)
        # A second occurrence is physically replayed as well. Keep one trace per content hash.
        if (self.out/'certificates'/(key+'.json')).exists():
            from heat import evaluate
            m=evaluate(self.p,plan,cert=True)
            assert m==g1io.read(self.out/'certificates'/(key+'.json'))['metrics']
        _,c=g1io.assess(self.p,plan);b=brief(c)
        before,low=original
        b.update(config_changes=sum(x[:2]!=y[:2] for x,y in zip(before,plan[0])),
                 start_changes=sum(x[2]!=y[2] for x,y in zip(before,plan[0])),gap_flag_changes=len(low^plan[1]))
        if self.age()<self.cap and improves(b,self.best):self.best=b;self.bestplan=plan
        return b
    def solve(self,plan,ids,permission,region,kind,bound,extra=None):
        left=min(29.4,bound-self.age()-3)
        if left<1:return False
        candidate,info=local(self.p,plan,ids,permission,left)
        row=dict(kind=kind,region=region,requests=ids,permission=permission,solver=info,**(extra or {}))
        if candidate is not None:row['result']=self.certify(candidate,plan)
        self.record(row)
        if info['status']=='ERROR':raise RuntimeError(info['traceback'])
        return True
    def diagnostic(self):
        base,low=self.seed;p=self.p
        for r in self.regions:
            for i in range(3*r['requests'][0],3*r['requests'][0]+3):
                for u,k in sorted(p.options[i]):
                    if self.age()>176:break
                    if (u,k)==base[i][:2]:continue
                    rows=list(base);rows[i]=(u,k,base[i][2])
                    b=self.certify((rows,low),self.seed)
                    self.record(dict(kind='single',region=r['id'],stage=i,from_option=base[i][:2],option=(u,k),result=b))
        for name,permission,bound in [('fixed',2,390),('joint',3,600)]:
            for turn in range(16):
                r=self.regions[turn%len(self.regions)]
                size=4 if turn<len(self.regions) else (2,3,4)[(turn-len(self.regions))%3]
                if not self.solve(self.seed,r['requests'][:size],permission,r['id'],name,bound):break
        rows=logs(self.folder/'candidates.jsonl')
        pool=[]
        for r in self.regions:
            pick=next((x for x in rows if x.get('region')==r['id'] and x['kind'] in ('single','fixed')
                       and x.get('result',{}).get('status')=='SAFE' and x['result']['plan']!=self.base['plan']),None)
            pool.append(dict(region=r['id'],plan=pick['result']['plan'] if pick else None,seq=pick['seq'] if pick else None))
        put(self.folder/'probe_pool.json',pool)
    def compare(self):
        from fifo import Compact
        from feedback import targets,neighborhood
        from common import decode
        root=RUN/self.case/'diagnostic'
        pool=read(root/'probe_pool.json')
        scores=[]
        for item in pool:
            gain35=gainfull=0
            if item['plan']:
                plan=native_plan(root/'physical/plans'/(item['plan']+'.json.gz'))
                b=self.certify(plan,self.seed)
                assert b['status']=='SAFE' and b['plan']==item['plan']
                gain35=self.base['E35']-b['E35'];gainfull=self.base['J']-b['J']
                self.record(dict(kind='shared_probe',region=item['region'],result=b))
            scores.append(dict(id=item['region'],gain35=gain35,gainfull=gainfull))
        ordered=sorted(scores,key=lambda x:(-x['gain35' if self.arm=='C' else 'gainfull'],x['id']))
        put(self.folder/'probe_scores.json',scores)
        model=Compact(self.p) if self.arm=='A' else None
        rng=random.Random(101);p=self.p
        for turn in range(16):
            if self.age()>self.cap-4:break
            size=(2,3,4)[turn%3];base=self.bestplan;cfg=[r[:2] for r in base[0][1::3]]
            extra=dict(incumbent=self.best['plan'])
            if self.arm=='A':
                groups=targets(model,cfg,101)
                groups=[[t for t in grp if len(t)<=size] for grp in groups]
                groups=[g for g in groups if g]
                if not groups:break
                g=groups[turn%len(groups)];t=g[(turn//len(groups))%len(g)]
                sel,_,feedback=neighborhood(model,cfg,t,'Proposed',size,min(self.start+self.cap-3,time.monotonic()+5))
                ids=sorted(sel);rid=None;extra.update(target=t,feedback=feedback)
            elif self.arm=='B':
                anchor=rng.randrange(len(p.req));center=base[0][3*anchor+1][2]
                ids=sorted(range(len(p.req)),key=lambda j:(abs(base[0][3*j+1][2]-center),j))[:size]
                rid=None;extra['anchor']=anchor
            else:
                rid=ordered[turn%len(ordered)]['id'];ids=self.regions[rid]['requests'][:size]
            assert len(ids)==size
            if not self.solve(base,ids,3,rid,'comparison',self.cap,extra):break
    def finish(self,status):
        put(self.folder/'receipt.json',dict(case=self.case,arm=self.arm,status=status,budget_s=self.cap,
            wall_s=self.age(),cpu_s=spent_cpu(),core=list(os.sched_getaffinity(0)),initial=self.base,best=self.best,
            records=self.n))
def main():
    start=time.monotonic();case,arm=sys.argv[1:];assert read(RUN/'preflight/receipt.json')['status']=='PASS'
    if arm!='diagnostic':assert read(RUN/'gate.json')['open']
    load_native(case)
    cell=Cell(case,arm,start)
    try:
        cell.diagnostic() if arm=='diagnostic' else cell.compare()
        cell.finish('COMPLETE')
    except BaseException:
        cell.record(dict(kind='interruption',error=traceback.format_exc()));cell.finish('INTERRUPTED');raise
if __name__=='__main__':main()
