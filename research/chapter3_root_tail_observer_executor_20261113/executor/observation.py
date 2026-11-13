"""Public observations, bounded storage, conservative clock alignment. No solver."""
import hashlib,json,os,threading,time
from pathlib import Path

HISTORY_LIMIT=100000
LOG_LIMIT=8*1024*1024
PROFILE_LIMIT=64*1024*1024
ALIGNMENT_LIMIT=.05

class OwnedSampler:
    def __init__(self,folder,start,process_module,clock=time.monotonic):
        self.folder=Path(folder); self.start=start; self.pm=process_module; self.clock=clock
        self.pid=os.getpid(); self.created=self.pm.Process(self.pid).create_time()
        self.known={self.pid:self.created}; self.errors=[]; self.rows=[]; self.arrivals=[]
        self.offset=0; self.truncated=False; self.cost_s=0.; self.stop_event=threading.Event()
        self.thread=None; self.started_at_s=clock()-start

    def start_thread(self):
        if self.thread: raise RuntimeError('Sampler already started')
        self.thread=threading.Thread(target=self._loop,name='D279-owned-observer',daemon=True)
        self.thread.start()

    def _loop(self):
        try:
            while not self.stop_event.is_set() and self.clock()<self.start+600:
                self.sample()
                self.stop_event.wait(1.)
        except Exception as e:
            self.errors.append(dict(elapsed_s=self.clock()-self.start,error='SAMPLER_THREAD: '+repr(e)))

    def sample(self):
        begin=self.clock()
        if begin>=self.start+600: return
        records=[]
        try:
            root=self.pm.Process(self.pid)
            if root.create_time()!=self.created: raise RuntimeError('SAMPLER_ROOT_PID_REUSED')
            for child in root.children(recursive=True):
                identity=child.create_time()
                if child.pid in self.known and self.known[child.pid]!=identity:
                    raise RuntimeError('OWNED_DESCENDANT_PID_REUSED')
                self.known[child.pid]=identity
            for pid,identity in list(self.known.items()):
                try:
                    p=self.pm.Process(pid)
                    if p.create_time()!=identity: raise RuntimeError('TRACKED_PID_REUSED')
                    cpu=p.cpu_times(); mem=p.memory_info(); io=p.io_counters()
                    records.append(dict(pid=pid,create_time=identity,cpu_user_s=cpu.user,
                        cpu_system_s=cpu.system,rss_bytes=mem.rss,vms_bytes=mem.vms,
                        io_read_bytes=io.read_bytes,io_write_bytes=io.write_bytes))
                except self.pm.NoSuchProcess: pass
        except Exception as e: self.errors.append(dict(elapsed_s=self.clock()-self.start,error=repr(e)))
        end=self.clock()
        if end<self.start+600:
            row=dict(start_elapsed_s=begin-self.start,read_completed_elapsed_s=end-self.start,processes=records)
            self.rows.append(row)
            with (self.folder/'owned_resources.jsonl').open('a',encoding='utf-8') as f:
                f.write(json.dumps(row,allow_nan=False)+'\n')
            self.read_log()
        self.cost_s+=self.clock()-begin

    def read_log(self):
        path=self.folder/'matlab/matlab.log'
        if not path.exists() or self.clock()>=self.start+600: return
        try:
            size=path.stat().st_size
            if size<self.offset: raise RuntimeError('LOG_SHRANK_OR_REPLACED')
            self.truncated |= size>LOG_LIMIT
            with path.open('rb') as f:
                f.seek(self.offset); data=f.read(min(65536,LOG_LIMIT-self.offset))
            if data and self.clock()<self.start+600:
                row=dict(byte_start=self.offset,byte_end=self.offset+len(data),
                    received_elapsed_s=self.clock()-self.start,sha256=hashlib.sha256(data).hexdigest())
                with (self.folder/'display_prefix.bin').open('ab') as f: f.write(data)
                self.arrivals.append(row);self.offset+=len(data)
        except Exception as e: self.errors.append(dict(elapsed_s=self.clock()-self.start,error=repr(e)))

    def stop(self):
        self.stop_event.set()
        if self.thread: self.thread.join(timeout=2)
        alive=bool(self.thread and self.thread.is_alive())
        # Final drain is charged and never waits for a buffer flush.
        if not alive:
            before=-1
            while self.offset!=before and self.clock()<self.start+600 and self.offset<LOG_LIMIT:
                before=self.offset;self.read_log()
        data=(self.folder/'display_prefix.bin').read_bytes() if (self.folder/'display_prefix.bin').exists() and not alive and self.clock()<self.start+600 else b''
        return dict(complete=not alive and not self.errors,thread_alive=alive,errors=self.errors,
            sample_count=len(self.rows),samples=self.rows,known_identities=self.known,
            measured_collection_wall_s=self.cost_s,log_arrivals=self.arrivals,log_bytes=self.offset,
            log_truncated=self.truncated,log_native_end_seen=b'D279_NATIVE_END' in data,
            log_has_additional_text=bool(data.replace(b'D279_NATIVE_BEGIN',b'').replace(b'D279_NATIVE_END',b'').strip()),
            started_at_elapsed_s=self.started_at_s,finished_at_elapsed_s=self.clock()-self.start,
            timing_semantics='Log arrival intervals only. Collection wall time overlaps native wall; never add twice.',
            overhead_unknown='Profiler observer effect, stdout overhead and OS perturbation cannot be measured by this single run')

def analyze_profile(profile,observation,marker_file='native/solve_model.m'):
    import numpy as np
    hist=np.asarray(profile.get('FunctionHistory',[]),dtype=float)
    table=profile.get('FunctionTable',[])
    if isinstance(table,dict): table=[table]
    elif isinstance(table,np.ndarray): table=table.reshape(-1).tolist()
    else: table=list(table)
    partial=any(bool(t.get('PartialData',False)) for t in table)
    result=dict(function_count=len(table),history_events=0,history_complete=False,
        partial_function_data=partial,alignment='UNKNOWN',exclusive_intervals=[],
        inclusive_times_must_not_be_summed=True,profiler_Overhead_is_not_a_measurement=True)
    if hist.ndim!=2 or hist.shape[0]!=4 or not np.isfinite(hist).all():
        return dict(result,reason='TIMESTAMP_HISTORY_SCHEMA_OR_FINITE_CHECK_FAILED')
    count=hist.shape[1]; result['history_events']=count
    result['history_capacity_reached']=count>=HISTORY_LIMIT
    if (hist[0]!=np.floor(hist[0])).any() or not np.isin(hist[0],[0,1]).all():
        return dict(result,reason='BAD_EVENT_KIND')
    if (hist[1]!=np.floor(hist[1])).any() or (hist[1]<1).any() or (hist[1]>len(table)).any():
        return dict(result,reason='BAD_FUNCTION_INDEX')
    times=hist[2]+hist[3]/1e6
    if (np.diff(times)<0).any(): return dict(result,reason='NONMONOTONIC_PROFILE_CLOCK')
    anchors=observation.get('anchors',[])
    if isinstance(anchors,dict): anchors=[anchors]
    offsets=[]; anchor_checks=[]; marker_indices={}
    for a in anchors:
        label=a['label']; suffix='d279_'+label+'_marker'
        matches=[j+1 for j,t in enumerate(table) if str(t.get('FunctionName','')).split('>')[-1].split('/')[-1]==suffix
                 and os.path.normcase(os.path.abspath(str(t.get('FileName',''))))==os.path.normcase(os.path.abspath(str(marker_file)))]
        entries=[i for i in range(count) if int(hist[1,i]) in matches and hist[0,i]==0]
        if len(entries)!=1 or not (0<=a['before_s']<=a['inside_s']<=a['after_s']):
            anchor_checks.append(False); continue
        epoch=float(times[entries[0]])
        offsets.append((a['before_s']-epoch-1e-5,a['after_s']-epoch+1e-5))
        marker_indices[label]=entries[0]
        anchor_checks.append(True)
    required={'begin','root','end'}
    if not required.issubset({a['label'] for a in anchors}) or not all(anchor_checks) or not offsets:
        return dict(result,reason='MISSING_OR_AMBIGUOUS_ANCHORS')
    lo=max(v[0] for v in offsets);hi=min(v[1] for v in offsets)
    if lo>hi or hi-lo>ALIGNMENT_LIMIT or any(b-a>ALIGNMENT_LIMIT for a,b in offsets):
        return dict(result,reason='CLOCK_OFFSET_INCONSISTENT_OR_UNCERTAIN')
    # profile('info') itself stops recording mid-call. Global nesting can therefore
    # be open without history overflow. Require balance only over the complete
    # named begin-to-end interval; never invent closure for a call inside it.
    first=marker_indices['begin'];end_entry=marker_indices['end']
    end_exits=[i for i in range(end_entry+1,count) if hist[0,i]==1 and hist[1,i]==hist[1,end_entry]]
    if not end_exits or not first<marker_indices['root']<end_entry:
        return dict(result,reason='MISSING_OR_REORDERED_MARKER_CLOSURE')
    last=end_exits[0];stack=[];spans=[];balanced=True
    for i in range(first,last+1):
        fid=int(hist[1,i]);t=float(times[i])
        if stack and i>first and t>float(times[i-1]): spans.append([stack[-1],float(times[i-1]),t])
        if hist[0,i]==0: stack.append(fid)
        elif stack and stack[-1]==fid: stack.pop()
        else: balanced=False;stack=[]
    balanced &= not stack
    result['history_complete']=bool(count<HISTORY_LIMIT and balanced and not partial)
    result['nesting_balanced']=balanced
    result['history_completeness_scope']='Named begin-to-end interval, not the profiler startup/snapshot boundary calls'
    result.update(alignment='BOUNDED',offset_interval_s=[lo,hi],marker_sources_verified=True,
        exclusive_intervals=[dict(function_index=f,start_request_s=[a+lo,a+hi],end_request_s=[b+lo,b+hi]) for f,a,b in spans],
        function_index=[dict(index=j+1,name=t.get('FunctionName'),file=t.get('FileName'),type=t.get('Type'),
            inclusive_s=float(t.get('TotalTime',0)),partial=bool(t.get('PartialData',False))) for j,t in enumerate(table)])
    # Names or aggregate protected calls never provide mechanism semantics.
    return result

def request_clock_alignment(events,publication_start):
    """Bound native request-tic origin on Python elapsed clock; never use arrival as event time."""
    import math
    if not isinstance(publication_start,(float,int)): return dict(state='UNKNOWN',reason='NO_PUBLICATION_BRACKET')
    offsets=[]
    for e in events:
        received=e.get('received_elapsed_s');native=e.get('request_wall_seconds')
        if isinstance(received,(int,float)) and isinstance(native,(int,float)) and math.isfinite(native) and 0<=received<550 and native>=0:
            offsets.append(received-native)
    if not offsets: return dict(state='UNKNOWN',reason='NO_NATIVE_CLOCK_EVENTS')
    lo=publication_start;hi=min(offsets)
    return dict(state='BOUNDED' if 0<=hi-lo<=ALIGNMENT_LIMIT else 'UNKNOWN',origin_interval_elapsed_s=[lo,hi],
        uncertainty_s=hi-lo,scope='Transport causal bracket, assumes tic and monotonic seconds keep rate; no exact clock synchronization')

def grade(packet,identity_verified,timely_archive,cleanup_complete):
    p=packet.get('profile_analysis',{}); s=packet.get('sampler',{})
    o0=bool(identity_verified and timely_archive and cleanup_complete and packet.get('response_timely')
        and packet.get('native_settings_verified') and packet.get('profile_packet_timely')
        and packet.get('profile_settings_verified') and not packet.get('error') and s.get('complete'))
    informative=bool((p.get('function_count',0)>0 and packet.get('root_observed')) or
        packet.get('post_root_resource_samples',0)>=2 or (s.get('log_has_additional_text') and packet.get('root_observed')))
    return dict(O0=o0,O1=bool(o0 and informative),O2='NOT_ESTABLISHED',
        O2_review_eligible=bool(o0 and informative and p.get('history_complete') and p.get('alignment')=='BOUNDED'),
        resource_profile_alignment=packet.get('request_clock_alignment',{'state':'UNKNOWN'}),
        concrete_bottleneck='UNKNOWN',targeted_intervention_eligible=False,
        next_action='Read-only semantic evidence review; no parameter scan or automatic next call',
        O2_rule='Independent review must bind visible timed exclusive intervals to verifiable function/source semantics, '
          'distinguish cuts/probing LP/branch handling/numerics/observer cost, rule out competing meanings, '
          'account for unobserved intervals, and identify >50% of aligned root-tail for a dominant-bottleneck claim. '
          'CPU load, inclusive protected-core time, zero nodes, absent callbacks, or guessed names never suffice. '
          'No O2 => UNKNOWN and stop parameter scanning. A proposal is not execution approval.')
