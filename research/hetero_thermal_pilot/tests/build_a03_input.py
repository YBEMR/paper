"""Build A03 exact-decimal abstract inputs. No simulation or optimizer.
All numerical values are assistant-selected L3 inputs, not measured values.
"""
from fractions import Fraction as F
from pathlib import Path
import argparse, json
ROOT=Path(__file__).resolve().parents[1]

def dec(x):
    x=F(x); d=x.denominator; a=b=0
    while d%2==0: a+=1; d//=2
    while d%5==0: b+=1; d//=5
    if d!=1: raise ValueError('Input is not a terminating decimal')
    n=max(a,b); v=x.numerator*2**(n-a)*5**(n-b)
    if not n: return str(v)
    sign='-' if v<0 else ''; z=str(abs(v)).zfill(n+1)
    return sign+(z[:-n]+'.'+z[-n:]).rstrip('0').rstrip('.')

def dumps(x,level=0):
    pad='  '*level; nxt='  '*(level+1)
    if isinstance(x,dict): return '{\n'+',\n'.join(nxt+json.dumps(k,ensure_ascii=False)+': '+dumps(v,level+1) for k,v in x.items())+'\n'+pad+'}'
    if isinstance(x,list):
        if not x: return '[]'
        if all(not isinstance(v,(dict,list)) for v in x): return '['+', '.join(dumps(v,level+1) for v in x)+']'
        return '[\n'+',\n'.join(nxt+dumps(v,level+1) for v in x)+'\n'+pad+']'
    if isinstance(x,bool) or x is None or isinstance(x,str): return json.dumps(x,ensure_ascii=False)
    return dec(x)

def opp(k,f,v,b,l): return dict(id=k,frequency_Hz=f,voltage_V=F(v),baseline_per_unit_W=F(b),local_leakage_W_per_K=F(l))
def build():
    domains=[
      dict(id='C',device_type='CPU',unit_ids=['CPU0','CPU1'],opps=[opp('L',10**9,'.75','.10','.002'),opp('H',2*10**9,'.95','.16','.003')]),
      dict(id='G',device_type='GPU',unit_ids=['GPU0'],opps=[opp('L',250000000,'.70','.18','.004'),opp('M',500000000,'.75','.24','.005'),opp('H',10**9,'.85','.32','.006')]),
      dict(id='N',device_type='NPU',unit_ids=['NPU0'],opps=[opp('L',250000000,'.65','.14','.003'),opp('M',500000000,'.65','.19','.004'),opp('H',10**9,'.80','.26','.005')])]
    units=[dict(id=u,device_type=d['device_type'],domain_id=d['id'],thermal_node=u) for d in domains for u in d['unit_ids']]
    def alpha(dref,sens): return dict(kind='alpha',dref_s=F(dref,1024),fref_Hz=2*10**9,sensitivity=F(sens))
    def profile(i,t,r,a,shared): return dict(id=i,device_type=t,response=r,activity=a,shared_activity_W=list(map(F,shared)))
    def cap(x): return dict(model='effective_capacitance',coefficient_F=F(x))
    def gpu(u): return dict(model='utilization_scaled_capacitance',capacitance_F=F('0.000000003'),utilization_by_opp=list(map(F,u)))
    profiles=[
      profile('host_pre_C','CPU',alpha(16,'.5'),cap('0.00000000018'),['.02','.04']),
      profile('host_post_C','CPU',alpha(8,'.25'),cap('0.00000000010'),['.015','.03']),
      profile('matrix_C','CPU',alpha(64,'.875'),cap('0.00000000060'),['.06','.10']),
      profile('memory_C','CPU',alpha(32,'.125'),cap('0.00000000025'),['.15','.20']),
      profile('matrix_G','GPU',dict(kind='table',duration_s=[F(x,1024) for x in [64,48,40]]),gpu(['.55']*3),['.20','.30','.40']),
      profile('memory_G','GPU',dict(kind='table',duration_s=[F(x,1024) for x in [32,30,29]]),gpu(['.20']*3),['.60','.65','.70']),
      profile('matrix_N','NPU',dict(kind='cycles_pwl',a_s=[F('.03125'),F('.0078125')],b_cycles=[0,15625000]),cap('0.0000000018'),['.20','.28','.32']),
      profile('memory_N','NPU',dict(kind='cycles_pwl',a_s=[F('.03515625'),F('.00390625')],b_cycles=[0,7812500]),cap('0.0000000008'),['.55','.58','.60'])]
    for pr in profiles:
        dom=next(d for d in domains if d['device_type']==pr['device_type'])
        pr['response']['freq_Hz']=[o['frequency_Hz'] for o in dom['opps']]
    stages=[]
    for request,main in [('A','matrix'),('B','memory')]:
        stages.extend([
          dict(id=request+'.pre',request_id=request,predecessors=[],profile_ids=['host_pre_C']),
          dict(id=request+'.main',request_id=request,predecessors=[request+'.pre'],profile_ids=[main+'_C',main+'_G',main+'_N']),
          dict(id=request+'.post',request_id=request,predecessors=[request+'.main'],profile_ids=['host_post_C'])])
    def duration(r,f,j):
        if r['kind']=='alpha': return r['dref_s']*(1-r['sensitivity']+r['sensitivity']*F(r['fref_Hz'],f))
        if r['kind']=='table': return r['duration_s'][j]
        return max(a+b/F(f) for a,b in zip(r['a_s'],r['b_cycles']))
    modes=[]
    for stage in stages:
        for pid in stage['profile_ids']:
            pr=next(p for p in profiles if p['id']==pid)
            dom=next(d for d in domains if d['device_type']==pr['device_type'])
            for unit in dom['unit_ids']:
                for j,o in enumerate(dom['opps']):
                    a=pr['activity']; c=a.get('coefficient_F',a.get('capacitance_F'))
                    if a['model']=='utilization_scaled_capacitance': c*=a['utilization_by_opp'][j]
                    modes.append(dict(id=stage['id']+'@'+unit+'@'+o['id'],stage_id=stage['id'],profile_id=pid,unit_id=unit,domain_id=dom['id'],opp_id=o['id'],duration_s=duration(pr['response'],o['frequency_Hz'],j),local_activity_W=c*o['frequency_Hz']*o['voltage_V']**2,shared_activity_W=pr['shared_activity_W'][j]))
    nodes=['CPU0','CPU1','GPU0','NPU0','U']
    ambient=list(map(F,['.12','.12','.15','.14','.25']))
    edges=[(0,1,'.03'),(0,2,'.02'),(1,2,'.02'),(0,3,'.015'),(1,3,'.015'),(0,4,'.04'),(1,4,'.04'),(2,3,'.02'),(2,4,'.06'),(3,4,'.06')]
    g=[[F(0) for _ in nodes] for _ in nodes]
    for i,x in enumerate(ambient): g[i][i]=x
    for i,j,x in edges:
        x=F(x); g[i][j]=g[j][i]=-x; g[i][i]+=x; g[j][j]+=x
    def fixture(name,shift):
        entries=[('A.pre','CPU0','L',F(0)),('A.main','GPU0','M',F(24,1024)),('A.post','CPU0','L',F(72,1024)),('B.pre','CPU1','L',shift),('B.main','NPU0','M',shift+F(24,1024)),('B.post','CPU1','L',shift+F(60,1024))]
        return dict(id=name,purpose='TEST_ONLY legality and future evaluator plumbing; not a research comparison',entries=[dict(stage_id=i,mode_id=i+'@'+u+'@'+k,start_s=t) for i,u,k,t in entries])
    return dict(schema='htp.a03.v1',freeze_date='2026-10-21',data_grade='L3_PHYSICS_CONSTRAINED_ABSTRACT',
      purpose='Frozen input and evaluator precheck, not calibrated hardware or scheduling evidence',
      units=dict(time='s',frequency='Hz',voltage='V',power='W',energy='J',capacity='J/K',conductance='W/K',temperature='degC',temperature_difference='K'),
      model_boundary=dict(electrical='Four compute units plus shared memory/system equivalent; excludes unmodelled peripherals',heat='Each modelled electrical power source injects heat into its declared node with coefficient 1',internal_hotspots_covered=False,real_hardware_calibration=False),
      execution=dict(nonpreemptive=True,stage_opp_fixed=True,unit_exclusive=True,cpu_domain_same_opp_during_overlap=True,idle_domain_policy='IMMEDIATE_LOWEST_OPP',switch_time_s=0,switch_energy_J=0,duration_temperature_dependence=False,activity_additive=True,contention_slowdown=False,extra_handoff_cost=False,start_domain='CONTINUOUS_NONNEGATIVE',overlap_semantics='HALF_OPEN; process ends before starts at a coincident event',background_configuration='FIXED_ABSTRACT_PROFILE_A03'),
      frequency_domains=domains,execution_units=units,
      shared_system=dict(node='U',baseline_W=F('.65'),leakage_W_per_K=F('.003'),baseline_count=1,background_clock_is_a_decision=False,memory_activity_constant=False),
      workload=dict(window_s=1,requests=[dict(id=r,release_s=0,absolute_deadline_s=F('.5'),terminal_stage_ids=[r+'.post']) for r in ['A','B']],stages=stages,support_semantics='Declared abstract backend support, not measured operator compatibility'),
      profiles=profiles,mode_table=modes,
      thermal=dict(node_order=nodes,ambient_temperature_degC=25,reference_temperature_degC=25,initial_temperature_degC=[35]*5,limit_temperature_degC=[70,70,70,70,65],power_model_temperature_range_degC=[25,85],heat_capacity_J_per_K=list(map(F,['.4','.4','.7','.6','2'])),ambient_conductance_W_per_K=ambient,conductance_W_per_K=g),
      evaluation_request=dict(energy_interval_abs_width_J=F('.00000001'),energy_interval_rel_width=F('.00000001'),temperature_extrema_abs_width_K=F('.0001'),certify_entire_window=True,tail_idle_charged=True,safety_status_requires_continuous_enclosure=True,hardware_model_error_bound='NOT_AVAILABLE',implemented_in_a03=False),
      parameter_provenance=[
        dict(group='architecture_and_control',grade='USER_CONFIRMED_ABSTRACT_SCOPE',source='P06-P09 in README; no chip specification inferred'),
        dict(group='all_numerical_parameters_and_workload',grade='ASSISTANT_SELECTED_L3',source='Chosen once for input/interface consistency, before scheduling studies; no literature numeric values imported'),
        dict(group='GPU_activity_structure',grade='LITERATURE_GUIDED_FORM_ONLY',source='A02 gpu_hpca18, III-A/B equations 3-9; no temperature term attributed to HPCA'),
        dict(group='NPU_response_and_activity_structure',grade='LITERATURE_GUIDED_FORM_ONLY',source='A02 npu_asplos; max-affine cycles divided by frequency, not its practical fitter'),
        dict(group='thermal_and_local_leakage_structure',grade='LITERATURE_GUIDED_FORM_ONLY',source='A02 fdtm IV-A2 and hotspot 3.1-3.2; chosen R/C and lambda not calibrated')],
      schedule_fixtures=[fixture('parallel_reference',F(0)),fixture('B_shifted_62p5ms',F('.0625'))])

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--write',action='store_true'); args=ap.parse_args()
    target=ROOT/'inputs/a03_minimal_v1.json'; payload=dumps(build())+'\n'
    if args.write:
        if target.exists() and target.read_bytes()!=payload.encode('utf-8'):
            raise SystemExit('Refusing to overwrite existing frozen v1; create an explicit new version')
        if not target.exists(): target.write_text(payload,encoding='utf-8',newline='\n')
    else:
        if target.read_bytes()!=payload.encode('utf-8'): raise SystemExit('Frozen input differs from exact builder; do not overwrite silently')
    print(('WROTE' if args.write else 'MATCH')+' a03_minimal_v1.json; 36 modes; no simulation')
if __name__=='__main__': main()
