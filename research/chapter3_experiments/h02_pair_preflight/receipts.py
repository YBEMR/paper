"""Read-only receipt contracts; no schedule search or temperature propagation."""
from decimal import Decimal, Context, ROUND_FLOOR, ROUND_CEILING
from .common import require,exact,sha,timely,POLICY
TECHNICAL={'INTERFACE_ERROR','INTERNAL_CONSISTENCY_ERROR','NUMERICAL_ERROR','RESOURCE_LIMIT','INVALID_INPUT'}
COMPONENTS={'baseline','activity','external_common','temperature_correction'}

def technical_issues(value,path=()):
    """Nested scene errors survive aggregate UNRESOLVED/POINT_WITNESS labels."""
    out=[]
    if isinstance(value,dict):
        for key in ('state','reason'):
            if isinstance(value.get(key),str) and value[key] in TECHNICAL:
                out.append({'path':list(path+(key,)),'value':value[key]})
        if value.get('error_type'): out.append({'path':list(path+('error_type',)),'value':str(value['error_type'])})
        for k,v in value.items():
            if isinstance(v,(dict,list)): out.extend(technical_issues(v,path+(k,)))
    elif isinstance(value,list):
        for j,v in enumerate(value): out.extend(technical_issues(v,path+(j,)))
    return out

def interval(v):
    require(isinstance(v,list) and len(v)==2,'ENERGY_INTERVAL_SHAPE'); a,b=map(exact,v); require(0<=a<=b,'ENERGY_INTERVAL_ORDER'); return a,b


def external_common_energy_interval(scene,power_W,window_s):
    """Check constant external energy against its existing Decimal60 protocol.

    Exact P*W must be enclosed. For a nonpoint receipt, replay only the scalar
    directed conversion/addition at the saved panel boundaries, never the heat
    equations. This supplies a rounding envelope without an invented epsilon.
    Exact singleton receipts remain compatible with mock and legacy evidence.
    """
    power,window=exact(power_W),exact(window_s)
    require(power>=0 and window>0,'EXTERNAL_POWER_OR_WINDOW')
    lo,hi=interval(scene.get('energy_components_J',{}).get('external_common'))
    expected=power*window
    require(lo<=expected<=hi,'EXTERNAL_POWER_ACCOUNTING')
    if lo==hi: return lo,hi
    trace=scene.get('trace')
    require(isinstance(trace,list) and len(trace)>0,'EXTERNAL_ENERGY_TRACE')
    down=Context(prec=60,rounding=ROUND_FLOOR)
    up=Context(prec=60,rounding=ROUND_CEILING)
    lower=upper=Decimal(0); previous=exact(0)
    for panel in trace:
        require(isinstance(panel,dict) and 'time_s' in panel,'EXTERNAL_ENERGY_TRACE')
        end=exact(panel['time_s'])
        require(previous<end<=window,'EXTERNAL_ENERGY_TRACE')
        quantity=power*(end-previous)
        numerator,denominator=Decimal(quantity.numerator),Decimal(quantity.denominator)
        lower=down.add(lower,down.divide(numerator,denominator))
        upper=up.add(upper,up.divide(numerator,denominator))
        previous=end
    require(previous==window,'EXTERNAL_ENERGY_TRACE')
    require(exact(str(lower))<=lo<=hi<=exact(str(upper)),
            'EXTERNAL_ROUNDING_ENCLOSURE')
    return lo,hi


def safe_receipt(instance,candidate,receipt,accuracy,seconds):
    require(receipt.get('state')=='SAFE' and receipt.get('rankable_energy') is True,'NOT_SAFE_RECEIPT')
    require(timely(receipt.get('completed_at_elapsed_s'),seconds),'LATE_OR_INVALID_SAFE_TIMESTAMP')
    require(not technical_issues(receipt) and not receipt.get('violations'),'SAFE_TECHNICAL_OR_VIOLATION')
    require(receipt.get('problem_id')==instance['id'],'RECEIPT_PROBLEM_ID')
    require(receipt.get('evidence_identity')=={'input_sha256':sha(instance),'candidate_sha256':sha(candidate)},'RECEIPT_EVIDENCE_IDENTITY')
    require(receipt.get('control_policy')=={'idle_policy':POLICY,'idle_delay_ms':'0'},'RECEIPT_POLICY')
    require(receipt.get('numerical_protocol')=='directed-decimal60-taylor18-scaled100-v1','NUMERICAL_PROTOCOL')
    scenes={s['id']:s for s in instance['scenarios']}; results=receipt.get('scenes',{})
    require(set(results)==set(scenes),'INCOMPLETE_SCENE_RECEIPT')
    legality=receipt.get('legality',{}); require(legality.get('state')=='SCHEDULE_VALID_THERMAL_UNCHECKED' and set(legality.get('scenes',{}))==set(scenes),'RECEIPT_LEGALITY')
    low=high=exact(0)
    nodes=instance['platform']['node_order']; valid=list(map(exact,instance['platform']['power_model_temperature_range_degC']))
    for sid,scene in scenes.items():
        r=results[sid]; require(r.get('state')=='SAFE' and r.get('complete') is True and r.get('rankable_energy') is True and r.get('energy_accuracy_met') is True,'SCENE_NOT_COMPLETE_SAFE')
        require(exact(r['covered_until_s'])==exact(instance['window_ms'])/1000,'SCENE_WINDOW_COVERAGE')
        lo,hi=interval(r['energy_J']); allowed=max(exact(accuracy['energy_absolute_error_J']),exact(accuracy['energy_relative_error'])*max(0,lo)); require(hi-lo<=allowed,'SCENE_ENERGY_PRECISION')
        parts=r.get('energy_components_J',{}); require(set(parts)==COMPONENTS,'ENERGY_COMPONENTS')
        values=[interval(v) for v in parts.values()]
        require(lo<=sum(v[0] for v in values) and hi>=sum(v[1] for v in values),'SCENE_ENERGY_COMPONENT_ENCLOSURE')
        external_common_energy_interval(r,instance['platform']['external_common_power_W'],exact(instance['window_ms'])/1000)
        require(set(r.get('peaks_degC',{}))==set(r.get('minimum_degC',{}))==set(nodes),'TEMPERATURE_NODE_COVERAGE')
        for j,node in enumerate(nodes):
            a,b=interval(r['peaks_degC'][node]); c,d=interval(r['minimum_degC'][node]); limit=exact(scene['maximum_temperature_degC'][j]); entry=exact(scene['entry']['temperature_degC'][j])
            require(valid[0]<=c<=d<=valid[1] and valid[0]<=a<=b<=min(valid[1],limit),'CONTINUOUS_THERMAL_BOUNDS')
            require(c<=entry<=b and c<=a and d<=b and b-a<=exact(accuracy['temperature_enclosure_width_K']) and d-c<=exact(accuracy['temperature_enclosure_width_K']),'TEMPERATURE_RANGE_OR_PRECISION')
        weight=exact(scene['weight']); low+=weight*lo; high+=weight*hi
    lo,hi=interval(receipt['weighted_energy_J']); require(lo<=low and hi>=high,'WEIGHTED_ENERGY_ENCLOSURE')
    require(exact(receipt['safe_upper_bound_J'])==hi,'SAFE_UPPER_BOUND_MISMATCH')
    require(hi-lo<=max(exact(accuracy['energy_absolute_error_J']),exact(accuracy['energy_relative_error'])*max(0,lo)),'WEIGHTED_ENERGY_PRECISION')
    return {'lower':str(lo),'upper':str(hi),'all_scenes_complete':True}

def thermal_witness(instance,receipt,seconds):
    scenes={s['id']:s for s in instance['scenarios']}; nodes=instance['platform']['node_order']; valid=list(map(exact,instance['platform']['power_model_temperature_range_degC']))
    usable=[]
    for v in receipt.get('violations',[]):
        sid=v.get('scene_id'); node=v.get('node')
        require(sid in scenes and node in nodes,'VIOLATION_IDENTITY'); lo,hi=interval(v['temperature_degC']); limit=exact(scenes[sid]['maximum_temperature_degC'][nodes.index(node)])
        require(exact(v['limit_degC'])==limit and lo>limit and hi<=valid[1] and valid[0]<=lo,'VIOLATION_NOT_CERTIFIED_IN_MODEL_RANGE')
        require(0<=exact(v['time_s'])<=exact(instance['window_ms'])/1000,'VIOLATION_TIME')
        if timely(v.get('formed_at_elapsed_s'),seconds): usable.append(v)
    return usable
