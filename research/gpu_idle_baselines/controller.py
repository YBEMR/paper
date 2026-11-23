"""Causal idle controllers. No simulator, file, model, or future-timeline imports.

Only release/ready observations already emitted by the event engine enter here.
All times are integer ns. The periodic forecast is the last ready phase + 40 ms.
"""


class Control:
    def __init__(self,strategy,tau,energy,dwell,period,service_end,window):
        assert strategy in ('reactive','periodic')
        self.strategy=strategy;self.tau=tau;self.energy=energy;self.dwell=dwell
        self.period=period;self.service_end=service_end;self.window=window
        self.scene=None;self.jobs={};self.forecasts={};self.hold_until=0;self.log=[]

    def record(self,now,kind,**data):
        assert not self.log or now>=self.log[-1]['t_ns']
        row=dict(seq=len(self.log),t_ns=now,kind=kind,**data);self.log.append(row);return row['seq']

    def release(self,now,rid,app,release,scene,required):
        assert now==release and rid not in self.jobs
        if scene!=self.scene:
            self.scene=scene;self.forecasts.clear();self.hold_until=0
            self.record(now,'scene_reset',scene=scene)
        self.jobs[rid]=dict(app=app,release_ns=release,scene=scene,required=required)
        self.record(now,'release',rid=rid,**self.jobs[rid])

    def ready(self,now,rid,stage):
        job=self.jobs[rid]
        sample=self.record(now,'ready',rid=rid,stage=stage,offset_ns=now-job['release_ns'],**job)
        if self.strategy!='periodic' or job['required']!='H' or job['scene']!=self.scene:return
        next_release=job['release_ns']+self.period
        if next_release>=self.service_end:return
        key=(job['app'],stage)
        forecast=dict(scene=self.scene,app=job['app'],stage=stage,sample_seq=sample,
                      sample_rid=rid,sample_time_ns=now,next_release_ns=next_release,
                      predicted_ns=now+self.period,used=False)
        self.forecasts[key]=forecast
        self.record(now,'forecast',**forecast)

    def next_prediction(self,now):
        live=[]
        for p in self.forecasts.values():
            if p['used']:continue
            if p['predicted_ns']<now:
                p['used']=True;self.record(now,'forecast_expired',**p)
            else:live.append(p)
        return min(live,key=lambda p:(p['predicted_ns'],p['app'],p['stage'])) if live else None

    def consume(self,now,p,reason):
        assert p['sample_time_ns']<=now
        p['used']=True;self.hold_until=max(self.hold_until,p['predicted_ns']+self.dwell)
        self.record(now,reason,**p)

    def choose(self,now,mode,busy,required_ready,idle_since,stable_since):
        """Return (target clock or None, timer or None, reason). No future event data."""
        if busy or mode=='X':return None,None,None
        if required_ready is not None:
            if mode==required_ready:return None,None,None
            earliest=stable_since+self.dwell if mode=='L' else now
            if now<earliest:return None,earliest,'minimum_L_residency'
            return required_ready,None,'actual_ready'
        p=self.next_prediction(now) if self.strategy=='periodic' else None
        if mode=='L':
            if p is None:return None,None,None
            wake=max(p['predicted_ns']-self.tau,stable_since+self.dwell)
            if wake>now:return None,wake,'periodic_wake_timer'
            self.consume(now,p,'prediction_wake')
            return 'H',None,'periodic_prediction'
        wait_until=max(idle_since,stable_since)+self.dwell
        if now<wait_until:return None,wait_until,'idle_wait'
        if self.hold_until>now:return None,self.hold_until,'predicted_demand_hold'
        if p is not None:
            low_time=p['predicted_ns']-now-2*self.tau
            if low_time<self.dwell or .5*low_time*1e-9<=2*self.energy:
                self.consume(now,p,'prediction_keep_H')
                return None,self.hold_until,'short_predicted_gap'
        if now+self.tau<=self.window:return 'L',None,'idle_timeout'
        return None,None,None
