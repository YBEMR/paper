"""Exact internal snapshots at completed event boundaries; single incumbent."""
from copy import deepcopy
import inspect,time
from runtime import SceneReuse,IdentityError,digest,encoded

STATE=['theta','peaks','minima','witnesses','energy_parts','node_energy','theta_integrals','seen_violation','out']

def plain(value,I):
    if isinstance(value,I):return {'directed_decimal60_interval':value.data()}
    if isinstance(value,dict):return {k:plain(v,I) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [plain(v,I) for v in value]
    if isinstance(value,set):return {'set':sorted(value)}
    return value

def build_kernel(t):
    """Five checked insertions; original arithmetic/control statements retained."""
    src=inspect.getsource(t.evaluate_piecewise)
    replacements=[
      ("accuracy=None, budget=None, scene_id='fixture'):","accuracy=None, budget=None, scene_id='fixture', checkpoint=None, on_checkpoint=None):"),
      ('        seen_violation = set()\n','        seen_violation = set()\n'+
       '        if checkpoint is not None:\n'+''.join(f"            {k} = checkpoint['{k}']\n" for k in STATE)),
      ('        for i in range(n):\n            record_point(i, F(0), theta[i])\n',
       '        if checkpoint is None:\n            for i in range(n):\n                record_point(i, F(0), theta[i])\n'),
      ('        for segment_index, (segment, matrix, base, activity, slopes, external) in enumerate(prepared):\n',
       '        for segment_index, (segment, matrix, base, activity, slopes, external) in enumerate(prepared):\n'+
       "            if checkpoint is not None and segment_index < checkpoint['next_segment']:\n                continue\n"),
      ("                budget.mark('after_panel_commit')\n",
       "                budget.mark('after_panel_commit')\n"+
       '                if on_checkpoint is not None and panel_index == count-1:\n'+
       "                    on_checkpoint(dict(next_segment=segment_index+1, checkpoint_at_s=budget.elapsed, "+
       ', '.join(k+'='+k for k in STATE)+'))\n')]
    for before,after in replacements:
        if src.count(before)!=1:raise IdentityError('CHECKPOINT_TRANSFORM_SOURCE_DRIFT')
        src=src.replace(before,after,1)
    namespace=dict(t.__dict__);exec(compile(src,'<independent_exact_prefix_wrapper>','exec'),namespace)
    return namespace['evaluate_piecewise'],src

class PrefixReuse(SceneReuse):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.kernel,self.generated_source=build_kernel(self.t)
        self.incumbent={};self.current_sources={};self.new_sources={}
        self.metrics.update(prefix_queries=0,prefix_checkpoints_saved=0,prefix_payload_bytes=0,prefix_query_s=0.0)

    def evaluate(self,candidate):
        self.current_sources={};self.new_sources={}
        return super().evaluate(candidate)

    def scene(self,platform,entry,limits,segments,window_ms,accuracy=None,budget=None,scene_id='fixture'):
        if budget is not self.budget:raise IdentityError('CACHE_ROOT_MISMATCH')
        budget.check();begin=time.perf_counter()
        physical=[{k:v for k,v in s.items() if k!='active_stage_ids'} for s in segments]
        context=digest({'context':self.identity,'version':self.version,'platform':platform,'scene':scene_id,
             'entry':entry,'limits':limits,'window':window_ms,'accuracy':accuracy,'policy':self.instance.get('rules')})
        key=digest({'context':self.identity,'version':self.version,'platform':platform,'scene':scene_id,'entry':entry,
             'limits':limits,'segments':physical,'window':window_ms,'accuracy':accuracy,'policy':self.instance.get('rules')})
        record=self.cache.get(key);self.metrics['scene_queries']+=1
        if record is not None and digest(record['result'])!=record['result_sha256']:raise IdentityError('CORRUPT_SCENE_CERTIFICATE')
        self.metrics['query_s']+=time.perf_counter()-begin;budget.check()
        if record is not None:
            begin=time.perf_counter();result=deepcopy(record['result']);budget.check()
            self.metrics['restore_s']+=time.perf_counter()-begin;self.metrics['scene_hits']+=1
            self.metrics['avoided_scene_panels']+=len(result['trace'])
            self.current_sources[scene_id]=record['prefix_source']
            self.provenance.append({'kind':'scene','scene_id':scene_id,'source_candidate':record['candidate_sha256'],
              'source_complete_at_s':record['complete_at_s'],'reused_at_s':budget.elapsed,'key':key})
            return result
        begin=time.perf_counter();self.metrics['prefix_queries']+=1
        source=self.incumbent.get(scene_id);checkpoint=None;old_checkpoints=[];common=0
        if source is not None:
            if source['context']!=context:raise IdentityError('PREFIX_CONTEXT_DRIFT')
            if source['root']!=self.root:raise IdentityError('PREFIX_ROOT_DRIFT')
            if source['path_sha256']!=digest({'context':source['context'],'root':source['root'],'physical':source['physical']}):
                raise IdentityError('PREFIX_PATH_DRIFT')
            for a,b in zip(physical,source['physical']):
                if a!=b:break
                common+=1
            if common:
                eligible=[c for c in source['checkpoints'] if c['state']['next_segment']<=common]
                if eligible:
                    item=eligible[-1]
                    if digest(plain(item['state'],self.t.I))!=item['state_sha256']:raise IdentityError('CORRUPT_PREFIX_STATE')
                    if item['prefix_sha256']!=digest(physical[:item['state']['next_segment']]):raise IdentityError('PREFIX_POWER_PATH_MISMATCH')
                    if item['state']['out']['covered_until_s']!=str(self.t._q(physical[item['state']['next_segment']-1]['end_ms'])/1000):
                        raise IdentityError('PREFIX_COVERAGE_MISMATCH')
                    if not 0<=item['state']['checkpoint_at_s']<=source['complete_at_s']<budget.elapsed:
                        raise IdentityError('PREFIX_SOURCE_TIME')
                    old_checkpoints=eligible
                    self.metrics['prefix_query_s']+=time.perf_counter()-begin;begin=time.perf_counter()
                    checkpoint=deepcopy(item['state']);budget.check()
                    self.metrics['prefix_restore_s']+=time.perf_counter()-begin
                    self.metrics['prefix_hits']+=1;self.metrics['avoided_prefix_panels']+=len(checkpoint['out']['trace'])
                    self.provenance.append({'kind':'prefix','scene_id':scene_id,'source_candidate':source['candidate_sha256'],
                       'source_complete_at_s':source['complete_at_s'],'reused_at_s':budget.elapsed,
                       'checkpoint_sha256':item['state_sha256'],'next_segment':checkpoint['next_segment'],
                       'covered_until_s':checkpoint['out']['covered_until_s']})
        if checkpoint is None:self.metrics['prefix_query_s']+=time.perf_counter()-begin
        checkpoints=list(old_checkpoints)
        def capture(state):
            started=time.perf_counter();saved=deepcopy(state);wire=plain(saved,self.t.I)
            checkpoints.append({'state':saved,'state_sha256':digest(wire),
                                'prefix_sha256':digest(physical[:saved['next_segment']])})
            self.metrics['prefix_checkpoints_saved']+=1;self.metrics['prefix_payload_bytes']+=len(encoded(wire))
            self.metrics['prefix_save_s']+=time.perf_counter()-started
        result=self.kernel(platform,entry,limits,segments,window_ms,accuracy,budget,scene_id=scene_id,
                           checkpoint=checkpoint,on_checkpoint=capture)
        if result.get('state')=='SAFE' and result.get('complete'):
            self.pending.append((key,result))
            source={'context':context,'root':self.root,'physical':deepcopy(physical),'checkpoints':checkpoints,
                    'candidate_sha256':self.current_candidate,'complete_at_s':None,
                    'path_sha256':digest({'context':context,'root':self.root,'physical':physical})}
            self.new_sources[key]=source;self.current_sources[scene_id]=source
        return result

    def commit(self,receipt):
        pending_keys=[k for k,_ in self.pending]
        super().commit(receipt)
        if receipt.get('state')!='SAFE':return
        begin=time.perf_counter()
        for key in pending_keys:
            source=self.new_sources[key];source['complete_at_s']=receipt['completed_at_elapsed_s']
            self.cache[key]['prefix_source']=source
        self.metrics['prefix_save_s']+=time.perf_counter()-begin

    def promote(self):
        # Only after original safe_receipt acceptance and original strict ordering.
        if set(self.current_sources)!=set(s['id'] for s in self.instance['scenarios']):raise IdentityError('INCOMPLETE_PREFIX_INCUMBENT')
        self.incumbent=dict(self.current_sources)
