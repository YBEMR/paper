"""Saved C_noheur ONLY. No builder, initializer, pruning or transformation calls."""
from pathlib import Path
import os,sys,time
from guard import read,save,sha,verify_plan,verify_approval,environment_snapshot
from saved_adapter_base import Runtime as SavedRuntime,decode,digest,schedule_key
from budget_policy import ABC_DYNAMIC,ResponseBudget,box_objective_bound
from dispatch import allocate_at_publication
from observation import OwnedSampler,analyze_profile,request_clock_alignment,PROFILE_LIMIT

class Runtime(SavedRuntime):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.arm='C_noheur_observe';self.allocation=None;self.sampler=None
        self.profile_data=None;self.observation_packet={};self.sampler_receipt=None
        self.start_attempted=False;self.source_verified_in_window=False

    def prepare(self):
        if environment_snapshot()!=self.plan['environment']: raise ValueError('Environment drift')
        sys.path.insert(0,str(self.workspace/'work/stable_expression'))
        sys.path.insert(0,str(self.workspace/'work/equality_pair_source/research/chapter3_experiments'))
        import numpy as np
        import complement_gate,matlab_bridge
        from timing import MethodBudget
        from thermal import evaluate_candidate,Exhausted
        from schedules import validate_schedule
        self.cg=complement_gate;self.bridge=matlab_bridge;self.evaluate=evaluate_candidate
        self.Exhausted=Exhausted;self.validate_schedule=validate_schedule
        self.budget=MethodBudget(600);self.budget.start=self.start;self.budget.deadline=self.start+600
        with self.budget.phase('saved_input_read_and_admission'):
            full=self.workspace/'work/stable_expression/full';saved=self.workspace/self.plan['saved_directory']
            self.instance=read(full/'input_instance.json');self.config=read(full/'input_config.json')
            self.options=read(saved/'options.json')
            self.initial=read(saved/'initialization.json')['attempts'][0]['candidate']
            self.old=self.payload(saved/'original_zero_based.mat');self.old['intcon']+=1
            self.new=self.payload(saved/'matlab/request_000001.mat')
            self.certificate=read(saved/'representation_certificate.json')
            if self.cg.array_digest(self.old)!=self.certificate['source_array_sha256']: raise ValueError('Old arrays drift')
            if self.cg.array_digest(self.new)!=self.certificate['derived_array_sha256']: raise ValueError('New arrays drift')
            if not all(v is True for v in self.certificate['checks'].values()): raise ValueError('Prior proof incomplete')
            n=len(self.old['c'])
            for k in ('c','lb','ub','x0'):
                if not np.array_equal(self.old[k],self.new[k][:n]): raise ValueError('Original coordinate changed')
            if not np.array_equal(self.old['intcon'],self.new['intcon']): raise ValueError('Integer domain changed')
            if list(self.old['intcon'])!=list(range(len(self.options))): raise ValueError('Option indexing changed')
            if digest(self.instance)!=self.plan['input_identity'] or digest(self.initial)!=self.plan['initial_candidate_identity']:
                raise ValueError('R1 or common initialization drift')
            self.native_old=self.bridge._prepare(self.old,x0=self.old['x0'])
            self.native_new=self.bridge._prepare(self.new,x0=self.new['x0'])
            candidate,legality=decode(self.instance,self.options,self.old['x0'],1e-6,self.validate_schedule)
            if schedule_key(candidate)!=schedule_key(self.initial): raise ValueError('Initial schedule drift')
            self.scene_count=len(self.instance['scenarios']);self.objective_reference=self.objective(self.old['x0'])
            self.objective_lower_bound=box_objective_bound(self.old['c'],self.old['lb'],self.old['ub'])
            save(self.folder/'saved_input_admission.json',dict(original=self.native_old['x0_validation'],
                transformed=self.native_new['x0_validation'],legality=legality,
                scope='Saved matrix diagnostic, prior exact projection certificate hash-bound, no new transform/build',
                strict_vector_feasibility_proof=False,original_variables=n,derived_variables=len(self.new['c'])))
        self.check()

    def _evaluate(self,candidate,filename):
        if self.evaluations>=2: raise RuntimeError('Two complete evaluation attempts already consumed')
        self.evaluations+=1
        result=self._call(filename,self.evaluate,self.instance,candidate,self.config['accuracy_targets'],budget=self.budget)
        self.check()
        result['evidence_identity']=dict(input=digest(self.instance),candidate=digest(candidate))
        save(self.folder/(filename+'.json'),result);self.check()
        return result

    def evaluate_initial(self): return self._evaluate(self.initial,'initial_complete_evaluation')

    def _permit(self):
        verify_approval(read(self.folder.parent/'approval_consumed.json'),sha(self.plan_path))
        claim=read(self.folder/'claim.json');worker=read(self.folder/'worker_claim.json')
        if not (claim['arm']==self.arm and claim['plan_sha256']==sha(self.plan_path) and
            claim['parent_start_monotonic']==self.start and worker['pid']==os.getpid() and worker['start_monotonic']==self.start):
            raise PermissionError('Native entry not bound to current one-use claim')

    def start_native(self):
        self._permit()
        if self.start_attempted: raise RuntimeError('MATLAB startup already attempted')
        self.start_attempted=True
        import psutil
        self.sampler=OwnedSampler(self.folder,self.start,psutil);self.sampler.start_thread()
        original=self.bridge.HERE;self.bridge.HERE=self.package/'native'
        try: return super().start_native()
        finally: self.bridge.HERE=original

    def solve(self,cap):
        self._permit()
        if self.solve_attempted: raise RuntimeError('Native request already consumed')
        self.solve_attempted=True
        def record(a): self.allocation=a;save(self.folder/'publication_allocation.json',a)
        def publication(p): self.observation_packet['request_publication']=p
        with allocate_at_publication(self.bridge,lambda:self.elapsed,record,publication):
            result=self._call('native_request_total',self.session.solve,self.new,x0=self.new['x0'],
                budget=ResponseBudget(self.budget,ABC_DYNAMIC,time.monotonic),solver_max_time_s=None)
        self.poll(None)
        result['received_by_adapter_elapsed_s']=self.elapsed
        self.observation_packet['response_timely']=bool(result.get('budget_valid') and self.elapsed<550)
        # Complete profile read and byte identity before 550; parsing/classification uses the remaining method time.
        path=self.folder/'matlab/request_000001.profile.mat'
        self.observation_packet['profile_packet_timely']=False
        if self.observation_packet['response_timely'] and path.exists():
            if path.stat().st_size>PROFILE_LIMIT:
                self.observation_packet['error']='PROFILE_FILE_EXCEEDS_64_MIB'
            else:
                data=path.read_bytes()
                import hashlib
                self.observation_packet.update(profile_sha256=hashlib.sha256(data).hexdigest(),
                    profile_bytes=len(data),profile_read_elapsed_s=self.elapsed,profile_packet_timely=self.elapsed<550)
                if self.elapsed<550: self.profile_data=data
        save(self.folder/'native_receipt.json',result);self.check()
        return result

    def inspect_identity(self,native,after_cleanup=False):
        root=self.folder/'matlab';checks={}
        path=root/'request_000001.mat'
        checks['actual_arrays']=self.cg.array_digest(self.payload(path))==self.cg.array_digest(self.new) if path.exists() else None
        request=read(root/'request_000001.request.json') if (root/'request_000001.request.json').exists() else {}
        # Only the timely response passed by solve is scientific evidence. No late-file substitution.
        expected=dict(self.plan['native_options']);actual=native.get('options')
        allocated=(self.allocation or {}).get('native_seconds');used=(actual or {}).get('MaxTime')
        expected['MaxTime']=used
        checks['native_options']=bool(actual==expected and isinstance(used,(int,float)) and allocated and 0<used<=allocated) if actual else None
        checks['published_cap']=request.get('solver_max_time_s')==allocated and request.get('solver_max_time_s_declared')==allocated if request else None
        checks['matlab_release']=read(root/'ready.json').get('release')=='2023b' if (root/'ready.json').exists() else None
        session=read(root/'session.json') if (root/'session.json').exists() else {}
        checks['native_sources']=session.get('source_sha256')=={
            'solve_model.m':sha(self.package/'native/solve_model.m'),
            'matlab_bridge.py':sha(self.workspace/'work/equality_pair_source/research/chapter3_experiments/matlab_bridge.py')} if session else None
        self.check()
        state='INVALID' if False in checks.values() else ('VERIFIED' if all(v is True for v in checks.values()) else 'UNKNOWN')
        result=dict(state=state,checks=checks,checked_at_elapsed_s=self.elapsed)
        save(self.folder/'identity_checks.json',result);self.check()
        self.observation_packet['native_settings_verified']=checks['native_options'] is True
        return result

    def finish_observation(self,native):
        self.check()
        with self.budget.phase('observation_stop_read_parse_and_archive'):
            self.sampler_receipt=self.sampler.stop() if self.sampler else dict(complete=True,sample_count=0,scope='No sampler started')
            self.check()
            packet=self.observation_packet;packet['sampler']=self.sampler_receipt
            roots=[e['received_elapsed_s'] for e in self.events if e.get('values',{}).get('phase')=='rootlp']
            packet['root_observed']=bool(roots)
            packet['post_root_resource_samples']=sum(s['read_completed_elapsed_s']>min(roots)
                and s['read_completed_elapsed_s']<550 for s in self.sampler_receipt.get('samples',[])) if roots else 0
            packet['request_clock_alignment']=request_clock_alignment(self.events,
                packet.get('request_publication',{}).get('start_elapsed_s'))
            obs=(native or {}).get('observation',{});packet['native_observation']=obs
            st=obs.get('profile_status',{});after=obs.get('profile_status_after',{})
            packet['profile_settings_verified']=bool(st.get('ProfilerStatus')=='on' and st.get('HistoryTracking')=='timestamp'
                and st.get('HistorySize')==100000 and st.get('Timer')=='performance' and st.get('DetailLevel')=='mmex'
                and after.get('ProfilerStatus')=='off' and obs.get('profile_archived') and not obs.get('error'))
            if self.profile_data is not None:
                import io
                from scipy.io import loadmat
                try:
                    p=loadmat(io.BytesIO(self.profile_data),simplify_cells=True)['profileData']
                    packet['profile_analysis']=analyze_profile(p,obs,self.package/'native/solve_model.m')
                except Exception as e: packet['error']='PROFILE_PARSE: '+repr(e)
            self.check();save(self.folder/'observation_packet.json',packet);self.check()
        return packet

    def freeze(self,result):
        self.check()
        verify_plan(self.plan_path,self.workspace,self.package);self.check()
        self.source_verified_in_window=True
        manifest={}
        # Explicit scientific evidence only: never collect preferences, temp folders or credentials.
        paths=[p for p in self.folder.glob('*.json') if p.name not in ('claim.json','worker_claim.json','command.json')]
        paths+=list(self.folder.glob('*.jsonl'))+list(self.folder.glob('*.bin'))
        paths+=list((self.folder/'matlab').glob('request_000001.*')) if (self.folder/'matlab').exists() else []
        for p in sorted(set(paths)):
            if not p.is_file() or p.suffix in ('.tmp','.cancel'): continue
            self.check();before=p.stat();h=sha(p);after=p.stat();self.check()
            if before.st_size!=after.st_size or before.st_mtime_ns!=after.st_mtime_ns: raise ValueError('Evidence changed during archive')
            manifest[p.relative_to(self.folder).as_posix()]=dict(sha256=h,bytes=after.st_size,hashed_at_elapsed_s=self.elapsed,
                scope='Archival identity only; arrival/acceptance deadlines remain independently enforced')
        save(self.folder/'scientific_artifact_manifest.json',manifest);self.check()
        result['scientific_artifact_manifest_sha256']=sha(self.folder/'scientific_artifact_manifest.json');self.check()
        if self.budget:
            result['timing_before_archive']=self.budget.summary(self.elapsed)
            result['timing_before_archive']['clock_origin']='Parent entry before approval/hash reads, imports, process creation and all scientific/observation work'
        result['snapshot_started_elapsed_s']=self.elapsed
        path=self.folder/'scientific_snapshot.json';save(path,result)
        identity=sha(path);self.check()
        return dict(sha256=identity,path=path.name,completed_at_elapsed_s=self.elapsed)

    def close(self):
        self.method_stopped=self.elapsed
        if self.sampler and self.sampler_receipt is None:
            # Emergency stop cannot earn observation credit after method expiry.
            self.sampler_receipt=self.sampler.stop()
        result=super().close()
        result['complete']=bool(result.get('complete') and not (self.sampler_receipt or {}).get('thread_alive'))
        return result

    def verify_after(self):
        # Only revocation is allowed here. No reading late logs/profile/response/candidate files.
        return dict(state='VERIFIED' if self.source_verified_in_window else 'UNKNOWN',
                    source_unchanged_through_snapshot=self.source_verified_in_window,checked_at_elapsed_s=self.elapsed,
                    scientific_credit_created=False,post_window_file_reads=0,
                    scope='Reuses in-window verification; no claim of post-cleanup hash remeasurement')
