"""Fresh per-arm science; historical matrices/schedules/certificates are never loaded."""
from pathlib import Path
import numpy as np
from core import read,save,digest,IntegrityError,PreparationStop,WindowExpired,safe_interval
from validation import admit,decode,exact_objective,schedule_key
from transport_contract import MatrixPacket

class Backend:
    def __init__(self,root,clock):
        from representation import load_science
        self.milp,self.cg=load_science(root)
        from schedules import validate_schedule
        from thermal import evaluate_candidate,Exhausted
        from timing import MethodBudget
        from initial_schedule import iter_initial_candidates
        from initial_point import complete_initial_point
        self.validate=validate_schedule;self.evaluate=evaluate_candidate
        self.candidates=iter_initial_candidates;self.complete=complete_initial_point
        self.budget=MethodBudget(590,clock=clock.now)
        self.budget.start=clock.start;self.budget.deadline=clock.start+590
        self.exhausted=Exhausted
    def build(self,instance,config,flags,arm):
        from representation import build
        return build(self.milp,instance,config,flags,arm,self.budget)
    def reduction(self,model,config,arm):
        from representation import reduction_audit
        return reduction_audit(model,config,arm,self.budget)
    def transform(self,old,gates):
        from representation import certify
        return certify(self.cg,old,gates,self.budget)
    def export(self,model,x0):
        from representation import export
        return export(model,x0)
    def archive(self,out,old,new):
        from scipy.io import savemat
        for label,arrays in [('original',old),('complement',new)]:
            savemat(out/(label+'_zero_based.mat'),arrays,do_compression=True,oned_as='column')

class Science:
    def __init__(self,root,plan,out,clock,backend_factory=Backend):
        self.root=Path(root);self.plan=plan;self.out=Path(out);self.clock=clock
        self.arm=Path(out).name;self.evaluations=0;self.model_builds=0;self.phase_records=[]
        self.backend_factory=backend_factory;self.initial_evaluation=None;self.initial=None
    def phase(self,name,fn,*args,**kwargs):
        self.clock.check();start=self.clock.elapsed
        try:
            try:return fn(*args,**kwargs)
            except self.backend.exhausted as e:raise WindowExpired(str(e)) from e
        finally:
            self.phase_records.append(dict(stage=name,start_s=start,end_s=self.clock.elapsed))
            self.clock.check()
    def prepare(self):
        if self.arm not in ('A','B','C'):raise IntegrityError('Arm identity')
        self.clock.check();self.backend=self.backend_factory(self.root,self.clock)
        b=self.backend;self.budget=b.budget;self.validate=b.validate
        self.instance=read(self.root/'work/stable_expression/full/input_instance.json')
        self.config=read(self.root/'work/stable_expression/full/input_config.json')
        if digest(self.instance)!=self.plan['input_identity']:raise IntegrityError('Physical input drift')
        self.scenes=[s['id'] for s in self.instance['scenarios']]
        self.model_builds+=1
        if self.model_builds!=1:raise IntegrityError('No rebuild')
        self.model,self.gates=self.phase('fresh_full_model',b.build,self.instance,self.config,self.plan['baseline_flags'],self.arm)
        self.options=self.model.options
        audit=self.phase('fresh_reduction_certificate_replay',b.reduction,self.model,self.config,self.arm)
        save(self.out/'reduction_verification.json',audit)
        save(self.out/'model_summary.json',self.model.summary());save(self.out/'options.json',self.options)
        save(self.out/'gate_rows.json',[dict(row=i,gate=g) for i,g in self.gates.items()])
        attempts=[];x0=None;start=self.clock.elapsed
        try:
            for attempt in b.candidates(self.instance,budget=self.budget,max_attempts=3):
                self.clock.check();attempts.append(attempt)
                if attempt['status']!='COMPLETE_LEGAL_CANDIDATE':continue
                candidate=attempt['candidate']
                value=self.evaluate(candidate,'initial_attempt_%d.json'%len(attempts))
                attempt['evaluation']=value
                if safe_interval(value,self.scenes) is None:continue
                if digest(candidate)!=self.plan['initial_candidate_identity']:raise IntegrityError('Common initial schedule drift')
                self.initial=candidate;self.initial_evaluation=value
                complete=self.phase('complete_continuous_initial_point',b.complete,self.model,candidate,value,self.budget)
                x0=complete.pop('x0');attempt['completion']=complete
                break
        except b.exhausted as e:raise WindowExpired(str(e)) from e
        finally:
            self.phase_records.append(dict(stage='independent_initialization',start_s=start,end_s=self.clock.elapsed))
            save(self.out/'initialization.json',dict(attempts=attempts,independently_computed=True))
        if self.initial_evaluation is None:raise PreparationStop('INITIAL_SAFE_NOT_ESTABLISHED_NO_CALL')
        if x0 is None:raise PreparationStop('INITIAL_CONTINUOUS_POINT_REJECTED_NO_CALL')
        old=self.phase('original_export',b.export,self.model,x0)
        new,cert=self.phase('complement_transform_exact_projection',b.transform,old,self.gates)
        if not cert.get('checks') or not all(v is True for v in cert['checks'].values()):raise IntegrityError('Projection failed')
        save(self.out/'representation_certificate.json',cert)
        self.packets={}
        for name,data in [('original',old),('complement',new)]:
            self.packets[name]=MatrixPacket.read(data,intcon_base=0,sense='min',objective_constant=0.,column_ids=range(data['c'].size))
        self.old=self.packets['original'];self.new=self.packets['complement']
        if self.old.intcon.tolist()!=self.new.intcon.tolist() or self.old.intcon.tolist()!=list(range(len(self.options))):raise IntegrityError('Option/index identity')
        for name in ('c','lb','ub','x0'):
            if getattr(self.old,name).tobytes()!=getattr(self.new,name)[:self.old.n].tobytes():raise IntegrityError('Original prefix changed')
        if np.any(self.new.c[self.old.n:]!=0):raise IntegrityError('Added objective changed')
        self.initial_admission=self.validate_vector(self.new.x0,'initial_admission.json')
        if not self.initial_admission['passed'] or not self.initial_admission['same_initial']:raise PreparationStop('INITIAL_NUMERICAL_ADMISSION_REJECTED_NO_CALL')
        self.phase('full_original_and_complement_archive',b.archive,self.out,old,new)
        save(self.out/'input_identity.json',dict(arm=self.arm,input=digest(self.instance),initial=digest(self.initial),
            matrices={k:v.hashes() for k,v in self.packets.items()},projection_checks=cert['checks'],
            source='fresh_independent_build_initialization_and_certification',model_builds=self.model_builds))
        save(self.out/'initial_complete_evaluation.json',self.initial_evaluation);self.clock.check()
    def evaluate_initial(self):
        # Already freshly evaluated and charged during this worker's initialization.
        self.clock.check();return self.initial_evaluation
    def validate_vector(self,x,filename):
        self.clock.check();a=admit(self.new,x,self.clock.check);b=admit(self.old,np.asarray(x)[:self.old.n],self.clock.check)
        result=dict(passed=False,complement=a,original=b,legality=None,candidate=None,same_initial=None)
        if a['passed'] and b['passed']:
            try:
                candidate,legality=decode(self.instance,self.options,x,self.validate)
                result.update(passed=True,candidate=candidate,legality=legality,same_initial=schedule_key(candidate)==schedule_key(self.initial),
                    schedule_identity=digest(schedule_key(candidate)),objective_exact_binary64=str(exact_objective(self.new,x)))
            except ValueError as e:result['rejection']=str(e)
        result['completed_elapsed_s']=self.clock.elapsed;save(self.out/filename,result);self.clock.check();return result
    def evaluate(self,candidate,name):
        if self.evaluations>=4:raise IntegrityError('At most three initial evaluations and one final')
        self.evaluations+=1
        result=self.phase(name,self.backend.evaluate,self.instance,candidate,self.config['accuracy_targets'],budget=self.budget)
        result['evidence_identity']=dict(input_sha256=digest(self.instance),candidate_sha256=digest(candidate))
        result['archived_elapsed_s']=self.clock.elapsed;save(self.out/name,result);self.clock.check();return result

