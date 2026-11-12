"""Full fresh A/B/C pipeline. Imported only by a newly authorized, claimed worker."""
from pathlib import Path
from fractions import Fraction
import os,time
from guard import read,save,sha,verify_plan,verify_approval,environment_snapshot
from saved_adapter_base import Runtime as SavedRuntime,decode,schedule_key
from representation import load_science,build,export,certify,reduction_audit,digest,require
from budget_policy import ABC_DYNAMIC,ResponseBudget,box_objective_bound
from dispatch import allocate_at_publication
from control import PreparationStop
from evidence import full_safe

class Runtime(SavedRuntime):
    def __init__(self,*args,arm,**kwargs):
        super().__init__(*args,**kwargs);self.arm=arm;self.solver_evidence_cutoff_s=550
        self.allocation=None;self.model_builds=0
        self.trial=self.plan['trials'][arm];self.model_arm=self.trial['model_arm']

    def prepare(self):
        require(environment_snapshot()==self.plan['environment'],'Execution dependency environment drift')
        self.milp,self.cg=load_science(self.workspace)
        import matlab_bridge
        from timing import MethodBudget
        from thermal import Exhausted
        from schedules import validate_schedule
        self.bridge=matlab_bridge;self.Exhausted=Exhausted;self.validate_schedule=validate_schedule
        self.budget=MethodBudget(600);self.budget.start=self.start;self.budget.deadline=self.start+600
        self._call('fresh_pipeline',self._prepare_fresh)

    def _prepare_fresh(self):
        full=self.workspace/'work/stable_expression/full'
        with self.budget.phase('input_read_and_identity'):
            self.instance=read(full/'input_instance.json');self.config=read(full/'input_config.json')
            require(digest(self.instance)==self.plan['input_identity'],'Original R1 input identity drift')
            self.scene_count=len(self.instance['scenarios'])
        with self.budget.phase('fresh_full_build'):
            self.model_builds+=1
            if self.model_builds!=1:raise RuntimeError('No rebuild or retry')
            self.model,self.gates=build(self.milp,self.instance,self.config,self.plan['baseline_flags'],self.model_arm,self.budget)
            self.options=self.model.options
            self.check();self.model_completed_at_elapsed_s=self.elapsed
        with self.budget.phase('reduction_certificate_replay'):
            audit=reduction_audit(self.model,self.config,self.model_arm,self.budget)
            save(self.folder/'reduction_verification.json',audit)
        with self.budget.phase('model_evidence_archive'):
            save(self.folder/'model_summary.json',self.model.summary());save(self.folder/'options.json',self.options)
            save(self.folder/'gate_rows.json',[dict(row=i,gate=g) for i,g in self.gates.items()])
        from initial_schedule import iter_initial_candidates
        from initial_point import complete_initial_point
        self.initial=None;self.initial_evaluation=None;attempts=[]
        with self.budget.phase('independent_initialization'):
            for attempt in iter_initial_candidates(self.instance,budget=self.budget,max_attempts=3):
                attempts.append(attempt)
                if attempt['status']!='COMPLETE_LEGAL_CANDIDATE':continue
                candidate=attempt['candidate']
                evaluation=self._evaluate(candidate,'initial_evaluation_'+str(len(attempts)))
                attempt['evaluation']=evaluation
                if not full_safe(evaluation,self.scene_count):continue
                self.initial=candidate;self.initial_evaluation=evaluation
                # Same deterministic rule and first SAFE schedule is mandatory; no historical vector is loaded.
                require(digest(candidate)==self.plan['initial_candidate_identity'],'Common initial schedule drift')
                completion=complete_initial_point(self.model,candidate,evaluation,self.budget)
                x0=completion.pop('x0');attempt['completion']=completion
                save(self.folder/'initialization.json',dict(attempts=attempts,independently_computed=True))
                if x0 is None:raise PreparationStop('INITIAL_CONTINUOUS_POINT_REJECTED_NO_CALL')
                break
            else:
                save(self.folder/'initialization.json',dict(attempts=attempts,independently_computed=True))
                raise PreparationStop('INITIAL_SAFE_NOT_ESTABLISHED_NO_CALL')
        with self.budget.phase('original_export'):
            self.old=export(self.model,x0)
        with self.budget.phase('complement_transform_and_exact_projection'):
            self.new,self.certificate=certify(self.cg,self.old,self.gates,self.budget)
            save(self.folder/'representation_certificate.json',self.certificate)
            self.check();self.certificate_completed_at_elapsed_s=self.elapsed
        with self.budget.phase('old_new_initial_numerical_admission'):
            try:
                self.native_old=self.bridge._prepare(self.old,x0=self.old['x0'])
                self.native_new=self.bridge._prepare(self.new,x0=self.new['x0'])
            except self.bridge.InitialPointRejected as e:
                save(self.folder/'initial_admission_rejection.json',dict(reason=str(e),diagnostics=e.diagnostics))
                raise PreparationStop('INITIAL_NUMERICAL_ADMISSION_REJECTED_NO_CALL') from e
            candidate,legality=decode(self.instance,self.options,self.old['x0'],1e-6,self.validate_schedule)
            require(schedule_key(candidate)==schedule_key(self.initial),'Initial vector schedule identity')
            self.objective_reference=self.objective(self.old['x0'])
            self.objective_lower_bound=box_objective_bound(self.old['c'],self.old['lb'],self.old['ub'])
            save(self.folder/'initial_admission.json',dict(original=self.native_old['x0_validation'],
                transformed=self.native_new['x0_validation'],legality=legality,
                objective_reference_exact=self.objective_reference,strict_feasibility_proof=False))
        with self.budget.phase('original_matrix_archive'):
            from scipy.io import savemat
            # Local archive uses zero-based indices, explicitly separate from native request MAT.
            savemat(self.folder/'original_zero_based.mat',self.old,do_compression=True,oned_as='column')
        self.check()

    def start_native(self):
        # This changes only the predeclared script location; the bridge and model remain frozen.
        original_here=self.bridge.HERE
        if self.trial['Heuristics']=='none':self.bridge.HERE=self.package/'native_none'
        try:return super().start_native()
        finally:self.bridge.HERE=original_here

    def _evaluate(self,candidate,filename):
        if self.evaluations>=4:raise RuntimeError('At most three initial evaluations and one final evaluation')
        self.evaluations+=1
        result=self._call(filename,self.milp.evaluate_model_candidate,self.model,candidate,self.config['accuracy_targets'],self.budget)
        save(self.folder/(filename+'.json'),result)
        return result

    def evaluate_initial(self):return self.initial_evaluation

    def _permit(self):
        approval=read(self.folder.parent/'approval_consumed.json');verify_approval(approval,sha(self.plan_path))
        claim=read(self.folder/'claim.json');worker=read(self.folder/'worker_claim.json')
        require(claim['plan_sha256']==sha(self.plan_path) and claim['arm']==self.arm and
                claim['parent_start_monotonic']==self.start and worker['pid']==os.getpid() and
                worker['start_monotonic']==self.start,'Native entry lacks this independent arm claim')

    def solve(self,cap):
        self._permit()
        if self.solve_attempted:raise RuntimeError('Single request already consumed')
        self.solve_attempted=True
        def record(allocation):
            self.allocation=allocation;save(self.folder/'publication_allocation.json',allocation)
        with allocate_at_publication(self.bridge,lambda:self.elapsed,record):
            result=self._call('native_request_total',self.session.solve,self.new,x0=self.new['x0'],
                budget=ResponseBudget(self.budget,ABC_DYNAMIC,time.monotonic),solver_max_time_s=None)
        self.poll(None)
        if result.get('budget_valid'):
            for event in result.get('callbacks',[]):self.capture(event)
        result['received_by_adapter_elapsed_s']=self.elapsed
        save(self.folder/'native_receipt.json',result)
        return result

    def inspect_identity(self,native,after_cleanup=False):
        root=self.folder/'matlab';checks={}
        path=root/'request_000001.mat'
        checks['actual_arrays']=self.cg.array_digest(self.payload(path))==self.cg.array_digest(self.new) if path.exists() else None
        request=read(root/'request_000001.request.json') if (root/'request_000001.request.json').exists() else {}
        actual=read(root/'request_000001.response.json') if (root/'request_000001.response.json').exists() else native
        expected=dict(self.plan['native_options']);expected['Heuristics']=self.trial['Heuristics']
        allocated=(self.allocation or {}).get('native_seconds');expected['MaxTime']=allocated
        checks['native_options']=actual.get('options')==expected if 'options' in actual and allocated is not None else None
        checks['published_cap']=request.get('solver_max_time_s')==allocated and request.get('solver_max_time_s_declared')==allocated if request else None
        checks['matlab_release']=read(root/'ready.json').get('release')=='2023b' if (root/'ready.json').exists() else None
        script=(self.package/'native_none/solve_model.m' if self.trial['Heuristics']=='none' else self.workspace/'work/equality_pair_source/research/chapter3_experiments/solve_model.m')
        session=read(root/'session.json') if (root/'session.json').exists() else {}
        expected_sources={'solve_model.m':sha(script),'matlab_bridge.py':sha(self.workspace/'work/equality_pair_source/research/chapter3_experiments/matlab_bridge.py')}
        checks['native_script_and_bridge']=session.get('source_sha256')==expected_sources if session else None
        state='INVALID' if False in checks.values() else ('VERIFIED' if all(v is True for v in checks.values()) else 'UNKNOWN')
        result=dict(state=state,checks=checks,checked_at_elapsed_s=self.elapsed,post_cutoff=self.elapsed>=600)
        save(self.folder/('identity_checks_after_cleanup.json' if after_cleanup else 'identity_checks.json'),result)
        return result

    def verify_after(self):
        verify_plan(self.plan_path,self.workspace,self.package)
        if self.budget:
            timing=self.budget.summary(self.method_stopped)
            timing['clock_origin']='Independent parent arm entry before source checks, child imports and process launch'
            save(self.folder/'timing_after_cleanup.json',timing)
        identity=self.inspect_identity({},True) if self.solve_attempted else None
        return dict(state='VERIFIED',source_unchanged=True,native_identity_after=identity,checked_at_elapsed_s=self.elapsed)
