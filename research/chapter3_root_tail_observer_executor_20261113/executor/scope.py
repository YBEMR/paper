"""Cumulative stop scopes. A later successful trial cannot erase an earlier stop."""
class ScopeLedger:
    def __init__(self, order, trials):
        self.order=list(order); self.trials=trials; self.completed=[]
        self.blocked=set(); self.stop_all=False; self.history=[]

    def consume(self, trial, receipt, controller_intact=True):
        if trial in self.completed: raise ValueError('A trial cannot be consumed twice')
        self.completed.append(trial)
        r=receipt or {}
        affected=r.get('affected_arms',[])
        valid_names=set(self.order)|{v.get('model_arm') for v in self.trials.values()}
        malformed_scope=(r.get('fault_scope') not in (None,'ALL','ARM','TRIAL','FEATURE') or
            not isinstance(affected,list) or any(a not in valid_names for a in affected) or
            (r.get('fault_scope')=='FEATURE' and not affected))
        bad=(not controller_intact or not r.get('cleanup',{}).get('complete') or
             r.get('identity_after',{}).get('state')!='VERIFIED' or r.get('fault_scope')=='ALL' or malformed_scope)
        self.stop_all |= bad
        if malformed_scope: affected=[]
        if r.get('fault_scope') in ('ARM','TRIAL'): affected=list(affected)+[trial]
        self.blocked.update(affected)
        self.history.append(dict(trial=trial,stop_all=self.stop_all,blocked=sorted(self.blocked)))
        return self.pending()

    def pending(self):
        return [] if self.stop_all else [a for a in self.order if a not in self.completed and
            a not in self.blocked and self.trials.get(a,{}).get('model_arm') not in self.blocked]

    def snapshot(self):
        return dict(completed=self.completed,blocked=sorted(self.blocked),stop_all=self.stop_all,
                    pending=self.pending(),history=self.history)
