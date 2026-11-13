"""Independent finite proof replay on the freshly constructed C model; no solving."""
from fractions import Fraction as F
from itertools import product
import hashlib,json,math
from representation import require

def hd(v,ascii=True):
    return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=ascii,separators=(',',':'),default=str).encode()).hexdigest()

def q(x): return F.from_float(float(x))

def replay_joint(model,budget):
    from milp import Model
    from thermal import I
    from joint_state_support import verify_gate_off_rows
    report=model.preprocessing['joint_state_pruning']
    templates=report['audit_certificate_cache']['template_catalogue']
    verified={};rowcount=0
    # Recreate the exact exported gate-off rows from each complete template key.
    # This is certificate replay, not fresh thermal coefficients or trajectory evaluation.
    for identity,record in templates.items():
        budget.check(); key=record['complete_key'];require(hd(key,False)==identity,'Gate template hash')
        boxkey,coefficients=key
        namespace,ns,nt,layout,boxes,gatebounds=boxkey
        probe=Model(model.instance,budget);slots=[];mapped={}
        for slot,box in zip(layout,boxes):
            if slot not in mapped:
                mapped[slot]=probe.var('replay:'+str(slot),F(box[2]),F(box[3]))
            v=mapped[slot];slots.append(v)
            require((probe.lb[v].hex(),probe.ub[v].hex())==tuple(box[:2]),'Gate box export drift')
        gate=probe.var('replay:gate',integer=True)
        require((probe.lb[gate].hex(),probe.ub[gate].hex())==tuple(gatebounds),'Gate domain drift')
        require(len(coefficients)==nt+1,'Gate physical row coverage')
        for target,row in zip(slots[ns:],coefficients):
            probe.affine_conditional_eq(target,slots[:ns],[I(a,b) for a,b in row],gate,'replayed')
        proof=verify_gate_off_rows(probe.rows,probe.lb,probe.ub,gate)
        require(proof==record['proof'],'Gate proof replay mismatch')
        verified[identity]=proof;rowcount+=proof['checked_rows']
    certificates=states=deleted=witnesses=0
    for sid,scene in report['scenes'].items():
        budget.check();groups=scene['stage_onehot'];catalogue=scene['certificate_catalogue']
        for stage,g in groups.items():
            ys=g['option_variables'];indices=g['row_indices']
            require(hd([model.rows[i] for i in indices])==g['rows_sha256'],'One-hot row identity')
            require(all(y in model.integer and tuple(model.bounds[y])==(F(0),F(1)) for y in ys),'One-hot binary domain')
            for i,sign in zip(indices,[1,-1]):
                require(model.rows[i]['coef']=={y:float(sign) for y in ys} and q(model.rows[i]['rhs'])==sign,'One-hot equation')
        for identity,proof in catalogue.items():
            require(hd(proof)==identity,'Joint proof hash');certificates+=1
            if proof['rule']=='exact_stage_unique':
                g=groups[proof['stage']]
                require(all(proof[k]==v for k,v in g.items()),'One-hot proof binding')
                left,right=set(proof['left_variables']),set(proof['right_variables'])
                require(left and right and not left&right and left|right<=set(g['option_variables']),'Disjoint Stage proof')
            else:
                require(proof['rule']=='exported_dependency_path','Unknown joint rule')
                rows=[model.rows[i] for i in proof['row_indices']]
                require([hd(r) for r in rows]==proof['row_sha256'],'Dependency row binding')
                coef={}
                for row in rows:
                    for y,a in row['coef'].items():coef[y]=coef.get(y,F(0))+q(a)
                minima=proof['stage_minima']
                require({r['stage'] for r in minima}==set(groups) and len(minima)==len(groups),'Stage minimum coverage')
                lhs=F(0)
                for row in minima:
                    ys=row['option_variables']; require(ys and set(ys)<=set(groups[row['stage']]['option_variables']),'Restricted group')
                    value=min(coef.get(y,F(0)) for y in ys)
                    require(value==F(row['coefficient_minimum']),'Exact minimum');lhs+=value
                rhs=sum((q(r['rhs']) for r in rows),F(0))
                require(lhs==F(proof['minimum_lhs']) and rhs==F(proof['summed_rhs']) and lhs-rhs==F(proof['strict_margin']) and lhs>rhs,'Exact strict obstruction')
        meta=model.scenes[sid]
        options=[(o,y) for o,y in zip(model.options,model.option_vars) if o['scenario_id']==sid]
        require(len(scene['interval_reports'])==len(meta['events'])-1,'Interval coverage')
        for i,rec in enumerate(scene['interval_reports']):
            budget.check();left,right=meta['events'][i:i+2]
            active=[(o,y) for o,y in options if F(o['start_ms'])/1000<=left and F(o['end_ms'])/1000>=right]
            choices={d:{} for d in rec['domain_order']}
            for o,y in active:
                choices[o['domain_id']].setdefault(o['opp_id'],{}).setdefault((o['stage_instance_id'],o['unit_id']),[]).append(y)
            require([tuple(r['state']) for r in rec['states']]==meta['candidate_states'][i],'Candidate-state coverage')
            retained=[];removed=[]
            for row in rec['states']:
                states+=1
                if row['status']!='PROVED_UNREACHABLE':
                    retained.append(tuple(row['state']));continue
                deleted+=1;removed.append(row['state'])
                domains=[list(choices[d].get(opp,{}).values()) for d,opp in zip(rec['domain_order'],row['state']) if opp!='L']
                require(math.prod(map(len,domains))==row['support_product']==len(row['exhaustive_rejections']),'Exhaustive witness count')
                # Enumeration order is irrelevant; check the full unique Cartesian set.
                expected={tuple(tuple(v) for v in ws) for ws in product(*domains)}
                actual={tuple(tuple(v) for v in r['witness_variables']) for r in row['exhaustive_rejections']}
                require(expected==actual and len(actual)==len(row['exhaustive_rejections']),'Exhaustive witness coverage')
                for rej in row['exhaustive_rejections']:
                    witnesses+=1;p=catalogue[rej['certificate_id']];ws=[set(v) for v in rej['witness_variables']]
                    if p['rule']=='exact_stage_unique':
                        require(set(p['left_variables']) in ws and set(p['right_variables']) in ws,'Obstruction not applicable')
                    else:
                        for m in p['stage_minima']:
                            ys=set(m['option_variables']);full=set(groups[m['stage']]['option_variables'])
                            require(ys==full or any(w<=ys for w in ws),'Restricted minimum not justified by witness')
            require(retained==meta['states'][i],'Unknown state was removed')
            gate=rec['gate_off_audit']
            require([r['state'] for r in gate.get('states',[])]==removed and gate['states_checked']==len(removed),'Deleted gate coverage')
            for r in gate.get('states',[]):
                require(all(r[k]==v for k,v in verified[r['template_sha256']].items()),'Gate audit identity')
    return dict(passed=True,proofs=certificates,states=states,deleted_states=deleted,
        exhaustive_witnesses=witnesses,gate_templates=len(verified),replayed_gate_rows=rowcount,
        integer_projection_only=True,all_unknown_states_retained=True)
