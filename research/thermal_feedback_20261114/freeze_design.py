import hashlib,itertools,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
base={'id':'nominal','initial':[.75,.55],'g_scale':1.,'c_scale':1.,'coupling_scale':1.,'trip_confirm':.2,'release_confirm':.5}
cases=[base,{**base,'id':'cold','initial':[.2,.2]},{**base,'id':'hot','initial':[.95,.65]}]
for k,vals in [('g_scale',[1.5,.8]),('c_scale',[.7,1.3]),('coupling_scale',[0.])]:
    for v in vals:cases.append({**base,'id':k+'_'+str(v),k:v})
cases.append({**base,'id':'slow_thermal_control','trip_confirm':.5,'release_confirm':1.})
for g,c in itertools.product([.9,1.1],repeat=2):cases.append({**base,'id':f'box_g{g}_c{c}','g_scale':g,'c_scale':c})
templates=[]
for a,b,fx,fy in itertools.product([0,1],[0,1],[.5,1.],[.5,1.]):
    templates.append({'id':f'A{a}B{b}_X{fx:g}Y{fy:g}','map':[0,a,0,b],'frequency':[fx,fy]})
cfg={'status':'FROZEN_SYNTHETIC_NORMALIZED_NOT_HARDWARE_CALIBRATED','date':'2026-11-14','work':[.6,2.5,.8,5.],'rates':[[1.,1.,1.,1.3],[0.,2.,0.,1.]],'arrivals':[0.,8.,16.],'relative_deadline':8.,'main_horizon':24.,'tail':10.,'C':[4.,7.],'Genv':[.8,1.4],'Gcouple':.1,'idle_power':[.08,.1],'active_base':[.65,.7],'dynamic_coefficient':[.35,1.1],'leak_coefficient':[.03,.02],'external_power':.12,'trip':[1.,1.8],'release':[.8,1.5],'throttled_frequency':.5,'hardware_sample':.1,'frequency_transition_time':.02,'frequency_transition_energy':.002,'initial_requested_frequency':[.5,.5],'reactive_trip':.85,'reactive_release':.65,'dt':.02,'scenarios':cases,'templates':templates,'counterfactual_scenarios':['nominal','hot'],'scan_budget_seconds':240,'validation_budget_seconds':90,'investment_reference_pct':1.}
assert len(cases)==13 and len(templates)==16
(ROOT/'design.json').write_text(json.dumps(cfg,indent=2)+'\n',encoding='utf-8')
names=['PROTOCOL.md','freeze_design.py','design.json']
(ROOT/'design_freeze.json').write_text(json.dumps({'files':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names}},indent=2)+'\n')
print({'cases':len(cases),'templates':len(templates),'full_sequences':16**3})
