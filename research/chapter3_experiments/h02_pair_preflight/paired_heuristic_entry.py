"""Mock-only thin execute_heuristic lifecycle and sealed candidate export.
No automatic real backend is configured. The precheck guards all supplied mocks.
"""
from dataclasses import dataclass,field
from pathlib import Path
from unittest.mock import Mock
import json,uuid
from .common import BASE_SHA,POLICY,require,copy,exact,encoded,sha,byte_sha,candidate_identity,raw_candidate,timely,ContractError
from .paired_response_input_view import physical_projection,planner_packet,pair_audit,fresh_H
from .contracts import static_monotonicity_contract
from .receipts import safe_receipt,TECHNICAL,technical_issues

PUBLIC={'view','problem_id','source_commit_sha','planner','plan_sha256','config_sha256','physical_projection_sha256','support_sha256','scenario_sha256','policy_id','accuracy_sha256'}

def validate_packet(packet):
    require(set(packet)==PUBLIC and set(packet['planner'])=={'config','instance'},'PLANNER_PUBLIC_FIELD_ALLOWLIST')
    c,i=packet['planner']['config'],packet['planner']['instance']; v=packet['view']
    require(v in ('H','R') and packet['source_commit_sha']==BASE_SHA and i['id']==packet['problem_id'],'PLANNER_IDENTITY')
    require(sha(i)==packet['plan_sha256'] and sha(c)==packet['config_sha256'],'PLANNER_HASH')
    require(sha(physical_projection(c,i))==packet['physical_projection_sha256'] and sha(i['scenarios'])==packet['scenario_sha256'],'PLANNER_PHYSICAL_OR_SCENARIO_HASH')
    require(sha(c['accuracy_targets'])==packet['accuracy_sha256'] and packet['policy_id']==POLICY,'PLANNER_ACCURACY_OR_POLICY')
    require(c['defaults']['response_variant']==i['response_variant']==i['settings']['response_variant']==v,'PLANNER_RESPONSE_LABEL')
    if v=='R':
        require(all(exact(pr['alpha'])==1 for st in c['stage_catalog'] for pr in st['profiles'].values()),'R_CONFIG_H_ALPHA_LEAK')
        require(all(exact(m['alpha'])==1 for rows in i['stage_modes'].values() for m in rows),'R_MODE_H_ALPHA_LEAK')
        require(all(exact(a)==1 for a in i['catalog_duration_weighted_mean_alpha'].values()),'R_STATISTIC_H_ALPHA_LEAK')
    from .common import mode_index
    modes,_=mode_index(i)
    support=[dict(stage=k[0],unit=k[1],opp=k[2],mode_id=modes[k]['mode_id']) for k in sorted(modes)]
    require(sha(support)==packet['support_sha256'],'PLANNER_SUPPORT_HASH')
    return True

@dataclass
class MockBackend:
    runner: Mock
    evaluator: Mock
    search: Mock
    clock: object
    kind: str='MOCK_ONLY'
    def check(self):
        require(self.kind=='MOCK_ONLY' and all(isinstance(f,Mock) for f in (self.runner,self.evaluator,self.search)),'FORMAL_BACKEND_NOT_AUTHORIZED')

@dataclass
class StageARegistry:
    root: Path
    bindings: dict=field(default_factory=dict)
    allocated: dict=field(default_factory=dict)
    frozen: dict=field(default_factory=dict)
    audit_consumed: set=field(default_factory=set)
    stopped: bool=False
    stop_reason: str=None
    def stop(self,reason): self.stopped=True; self.stop_reason=reason
    def bind_pair(self,pair):
        # Controller only. Never pass this registry, H config or contract to R callbacks.
        c,h=fresh_H(pair['truth_H']['instance']['id'],pair['source_commit_sha'])
        require(pair['truth_H']=={'config':c,'instance':h},'TRUTH_DIFFERS_FROM_PINNED_SOURCE')
        report=pair_audit(pair['planner_H']['config'],pair['planner_H']['instance'],pair['planner_R']['config'],pair['planner_R']['instance'])
        contract=static_monotonicity_contract(c,h,pair['planner_R']['instance'])
        for view in ('H','R'):
            packet=planner_packet(pair,view)
            self.bindings[(h['id'],view)]=dict(packet_sha256=sha(packet),truth_H_sha256=sha(h),truth_H_config_sha256=sha(c),static_contract_sha256=sha(contract),p1_p2_static_passed=contract['passed'])
        return contract
    def reserve(self,slot,packet,truth_sha):
        require(not self.stopped,'STOP_LATCHED:'+str(self.stop_reason)); require(slot not in self.allocated,'DUPLICATE_PLAN_SLOT')
        require(isinstance(slot,str) and slot.replace('_','').replace('-','').isalnum(),'UNSAFE_SLOT_ID')
        binding=self.bindings.get((packet['problem_id'],packet['view']))
        require(binding and binding['packet_sha256']==sha(packet) and binding['truth_H_sha256']==truth_sha,'UNBOUND_OR_DRIFTED_PLANNER_CONTEXT')
        path=Path(self.root)/slot; require(not path.exists(),'REUSED_PLAN_DIRECTORY'); path.mkdir(parents=True)
        self.allocated[slot]=dict(binding,path=str(path))
        return path
    def verify(self,token):
        require(not self.stopped,'STOP_LATCHED:'+str(self.stop_reason)); key=token.get('token_id')
        require(key in self.frozen and token==self.frozen[key],'FROZEN_CANDIDATE_IDENTITY')
        require(key not in self.audit_consumed,'POST_AUDIT_ALREADY_CONSUMED')
        return key

def paired_heuristic_entry(packet,backend,registry,slot,truth_sha):
    backend.check(); validate_packet(packet); folder=registry.reserve(slot,packet,truth_sha)
    payload=encoded(packet['planner'])  # Loader closure captures only these public bytes.
    def input_loader(budget):
        budget.check(); public=json.loads(payload); return public['config'],public['instance']
    try:
        result=backend.runner(input_loader,folder/'planner',method='heft',seconds=120,seed=None,clock=backend.clock,evaluator=backend.evaluator,search=backend.search,allow_auto_low=True)
        require(sha(packet)==registry.allocated[slot]['packet_sha256'],'PLANNER_MUTATED_PUBLIC_INPUT')
        c,i=packet['planner']['config'],packet['planner']['instance']; candidate=result.get('safe_candidate')
        technical=bool(technical_issues(result))
        out=dict(evidence_kind='MOCK_ONLY',usable_as_research_evidence=False,plan_status='PLAN_UNRESOLVED',slot=slot,raw_method_result=copy(result),technical_failure=technical,stop_required=technical,frozen_candidate=None)
        if candidate is None:
            require(not any(r.get('accepted_safe') for r in result.get('evaluations',[])),'RECORDER_BEST_MISSING')
            out['plan_status']='PLAN_NO_SAFE' if result.get('reason')=='DECLARED_SEARCH_COMPLETED' and not technical else 'PLAN_UNRESOLVED'
        else:
            require(result.get('method')=='heft' and result.get('seed') is None and result.get('problem_id')==i['id'] and result.get('input_sha256')==sha(i),'METHOD_RESULT_IDENTITY')
            safe=[]
            for row in result.get('evaluations',[]):
                if row.get('accepted_safe') is True:
                    cand=row['candidate']; candidate_identity(i,cand); require(row.get('candidate_sha256')==sha(cand),'RECORDER_CANDIDATE_HASH')
                    safe_receipt(i,cand,row['evaluation'],c['accuracy_targets'],120); safe.append(row)
            require(safe,'NO_ACCEPTED_SAFE_RECORD'); best=min(safe,key=lambda r:exact(r['evaluation']['safe_upper_bound_J']))
            require(candidate==best['candidate'] and result.get('evaluation')==best['evaluation'] and exact(result['safe_upper_bound_J'])==exact(best['evaluation']['safe_upper_bound_J']),'NOT_CANDIDATE_RECORDER_BEST')
            identity=candidate_identity(i,candidate); raw=encoded(candidate)
            token=dict(token_id=uuid.uuid4().hex,evidence_kind='MOCK_ONLY',source_commit_sha=BASE_SHA,problem_id=i['id'],view=packet['view'],plan_sha256=packet['plan_sha256'],truth_H_sha256=truth_sha,
                physical_projection_sha256=packet['physical_projection_sha256'],policy_id=POLICY,accuracy_sha256=packet['accuracy_sha256'],candidate_raw_sha256=byte_sha(raw),candidate_semantic_sha256=identity['candidate_semantic_sha256'],
                candidate_json=raw.decode('utf-8'),planning_receipt_sha256=sha(best['evaluation']),plan_formed_at_elapsed_s=best['evaluation']['completed_at_elapsed_s'],p1_p2_static_passed=registry.allocated[slot]['p1_p2_static_passed'],static_contract_sha256=registry.allocated[slot]['static_contract_sha256'],truth_H_config_sha256=registry.allocated[slot]['truth_H_config_sha256'])
            registry.frozen[token['token_id']]=copy(token); out.update(plan_status='PLAN_SAFE',frozen_candidate=token)
            (folder/'frozen_mock_candidate.json').write_text(json.dumps(token,indent=2)+'\n',encoding='utf-8')
        if technical: registry.stop('PLANNER_TECHNICAL_FAILURE')
        return out
    except Exception as error:
        registry.stop(str(error)); return dict(evidence_kind='MOCK_ONLY',usable_as_research_evidence=False,plan_status='INPUT_OR_INTERFACE_ERROR',reason=str(error),stop_required=True,frozen_candidate=None)
