"""Isolated scene-certificate reuse. Frozen numerical functions stay unchanged."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib, importlib, json, sys, time
from pathlib import Path

def encoded(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')

def digest(value): return hashlib.sha256(encoded(value)).hexdigest()

class IdentityError(RuntimeError): pass

def load_frozen(cache):
    sys.dont_write_bytecode=True
    manifest=json.loads(Path(__file__).with_name('frozen_sources.json').read_text(encoding='utf-8'))
    for row in manifest['files']:
        if hashlib.sha256((cache/row['path']).read_bytes()).hexdigest()!=row['sha256']:
            raise IdentityError('FROZEN_SOURCE_DRIFT:'+row['path'])
    sys.path.insert(0,str(cache/'research/chapter3_experiments'))
    thermal=importlib.import_module('thermal')
    timing=importlib.import_module('timing')
    receipts=importlib.import_module('h02_pair_preflight.receipts')
    return thermal,timing,receipts,digest(manifest)

def semantic(value):
    excluded={'elapsed_s','completed_at_elapsed_s','formed_at_elapsed_s','panels','refinements','reuse_provenance'}
    if isinstance(value,dict):return {k:semantic(v) for k,v in value.items() if k not in excluded}
    if isinstance(value,list):return [semantic(v) for v in value]
    return value

def compact_receipt(receipt):
    out=deepcopy(receipt)
    for scene in out.get('scenes',{}).values():
        trace=scene.pop('trace',[]);scene['trace_sha256']=digest(trace);scene['trace_panels']=len(trace)
    legal=out.pop('legality',None)
    out['legality_sha256']=digest(legal)
    out['semantic_sha256']=digest(semantic(receipt))
    return out

@contextmanager
def count_extrema(thermal,budget):
    original=thermal.Panel.extremum
    def observed(panel,*args,**kwargs):
        budget.extremum_calls+=1
        return original(panel,*args,**kwargs)
    thermal.Panel.extremum=observed
    try:yield
    finally:thermal.Panel.extremum=original

class SceneReuse:
    def __init__(self,thermal,instance,config,budget,version,enabled=True):
        self.t=thermal;self.instance=instance;self.config=config;self.budget=budget
        self.enabled=enabled;self.version=version;self.identity=(digest(instance),digest(config))
        self.root=(id(budget),budget.start,budget.deadline,budget.seconds,budget.panel_limit,budget.refinement_limit)
        self.cache={};self.pending=[];self.current_candidate=None;self.provenance=[]
        self.metrics={k:0.0 for k in ['query_s','restore_s','save_s','identity_s','prefix_save_s','prefix_restore_s']}
        self.metrics.update(scene_queries=0,scene_hits=0,scene_saves=0,avoided_scene_panels=0,cache_payload_bytes=0,
                            prefix_hits=0,avoided_prefix_panels=0)
        self.original=thermal.evaluate_piecewise

    def check(self):
        begin=time.perf_counter()
        if self.identity!=(digest(self.instance),digest(self.config)) or self.root!=(id(self.budget),self.budget.start,self.budget.deadline,self.budget.seconds,self.budget.panel_limit,self.budget.refinement_limit):
            raise IdentityError('INPUT_OR_ROOT_DRIFT')
        self.budget.check();self.metrics['identity_s']+=time.perf_counter()-begin

    def scene(self,platform,entry,limits,segments,window_ms,accuracy=None,budget=None,scene_id='fixture'):
        if budget is not self.budget:raise IdentityError('CACHE_ROOT_MISMATCH')
        budget.check();start=time.perf_counter()
        physical=[{k:v for k,v in s.items() if k!='active_stage_ids'} for s in segments]
        key=digest({'context':self.identity,'version':self.version,'platform':platform,'scene':scene_id,'entry':entry,
                    'limits':limits,'segments':physical,'window':window_ms,'accuracy':accuracy,
                    'policy':self.instance.get('rules')})
        self.metrics['scene_queries']+=1
        record=self.cache.get(key)
        if record is not None and digest(record['result'])!=record['result_sha256']:
            raise IdentityError('CORRUPT_SCENE_CERTIFICATE')
        self.metrics['query_s']+=time.perf_counter()-start
        budget.check()
        if record is not None:
            begin=time.perf_counter();result=deepcopy(record['result'])
            budget.check()
            self.metrics['restore_s']+=time.perf_counter()-begin;self.metrics['scene_hits']+=1
            self.metrics['avoided_scene_panels']+=len(result['trace'])
            self.provenance.append({'kind':'scene','scene_id':scene_id,'source_candidate':record['candidate_sha256'],
                'source_complete_at_s':record['complete_at_s'],'reused_at_s':budget.elapsed,'key':key})
            return result
        result=self.original(platform,entry,limits,segments,window_ms,accuracy,budget,scene_id=scene_id)
        if result.get('state')=='SAFE' and result.get('complete'):
            self.pending.append((key,result))
        return result

    def evaluate(self,candidate):
        self.check();self.pending=[];self.provenance=[];self.current_candidate=digest(candidate)
        if not self.enabled:
            return self.t.evaluate_candidate(self.instance,candidate,self.config['accuracy_targets'],self.budget)
        original=self.t.evaluate_piecewise;self.t.evaluate_piecewise=self.scene
        try:
            result=self.t.evaluate_candidate(self.instance,candidate,self.config['accuracy_targets'],self.budget)
        finally:self.t.evaluate_piecewise=original
        result['reuse_provenance']=deepcopy(self.provenance)
        return result

    def commit(self,receipt):
        # The caller must independently accept the complete new receipt first.
        if not self.enabled or receipt.get('state')!='SAFE':self.pending=[];return
        if receipt.get('evidence_identity')!={'input_sha256':self.identity[0],'candidate_sha256':self.current_candidate}:
            raise IdentityError('NEW_RECEIPT_IDENTITY')
        if not 0<=receipt['completed_at_elapsed_s']<self.budget.seconds:
            raise IdentityError('LATE_NEW_CERTIFICATE')
        begin=time.perf_counter()
        for key,result in self.pending:
            saved=deepcopy(result)
            self.cache[key]={'result':saved,'result_sha256':digest(saved),'candidate_sha256':self.current_candidate,
                'complete_at_s':receipt['completed_at_elapsed_s']}
            self.metrics['scene_saves']+=1;self.metrics['cache_payload_bytes']+=len(encoded(self.cache[key]))
        self.pending=[];self.metrics['save_s']+=time.perf_counter()-begin
