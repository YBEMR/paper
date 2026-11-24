"""Same reactive rule as af6dd97, with M accepted as a busy frequency."""
class Control:
    def __init__(self,strategy,tau,energy,dwell,period,service_end,window):
        assert strategy=='reactive'
        self.tau=tau;self.dwell=dwell;self.window=window;self.log=[]
    def record(self,now,kind,**data):
        self.log.append(dict(seq=len(self.log),t_ns=now,kind=kind,**data))
    def release(self,now,rid,app,release,scene,required):
        assert now==release
        self.record(now,'release',rid=rid,app=app,scene=scene,required=required)
    def ready(self,now,rid,stage):self.record(now,'ready',rid=rid,stage=stage)
    def choose(self,now,mode,busy,required_ready,idle_since,stable_since):
        if busy or mode=='X':return None,None,None
        if required_ready is not None:
            if mode==required_ready:return None,None,None
            earliest=stable_since+self.dwell if mode=='L' else now
            if now<earliest:return None,earliest,'minimum_L_residency'
            return required_ready,None,'actual_ready'
        if mode=='L':return None,None,None
        wait=max(idle_since,stable_since)+self.dwell
        if now<wait:return None,wait,'idle_wait'
        if now+self.tau<=self.window:return 'L',None,'idle_timeout'
        return None,None,None

class Timeline:
    def __init__(self,window):self.window=window;self.changes=[(0,'L')];self.switches=[]
    def switch(self,t,to,tau,energy):
        old=self.changes[-1][1]
        assert old in 'LMH' and to in 'LMH' and old!=to and t>=self.changes[-1][0] and t+tau<=self.window
        self.switches.append(dict(start_ns=t,end_ns=t+tau,source=old,target=to,energy_j=energy))
        if tau:self.changes.append((t,'X'))
        else:assert energy==0
        self.changes.append((t+tau,to))
    def spans(self):
        values=dict(self.changes);points=sorted(values)
        return [(a,points[i+1] if i+1<len(points) else self.window,values[a]) for i,a in enumerate(points) if a<self.window]
