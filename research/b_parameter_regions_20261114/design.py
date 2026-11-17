"""Predeclared scenarios. All numerical choices are synthetic, not AGX calibration."""
import hashlib,itertools,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def scenarios():
    result=[]
    def add(name,family,**changes):
        p=dict(leak_scale=1.,sleepcontrast=1.,wake_energy_J=.001,C_scale=1.,R_scale=1.,b2_time_scale=1.,b2_power_scale=1.,beta_scale=1.,wake_time_scale=1.,ambient_C=25.)
        p.update(changes)
        result.append(dict(id=name,family=family,**p))
    for leak,dpm,wake in itertools.product([0.,.5,1.,2.],[0.,.5,1.],[0.,.001,.01]):
        add(f'grid_L{leak:g}_D{dpm:g}_W{wake*1000:g}', 'factorial',leak_scale=leak,sleepcontrast=dpm,wake_energy_J=wake)
    add('temperature_independent','negative_control',beta_scale=0.)
    for key,values in [('C_scale',[.5,2.]),('R_scale',[.5,2.]),('b2_time_scale',[.8,1.2]),('b2_power_scale',[.8,1.2]),('beta_scale',[.5,1.5]),('wake_time_scale',[.5,2.]),('ambient_C',[20.,30.])]:
        for val in values:add(f'OAT_{key}_{val:g}','one_at_a_time',**{key:val})
    for i,(t,p,l,w) in enumerate(itertools.product([.9,1.1],[.9,1.1],[.8,1.2],[.0005,.0015])):
        add(f'box_{i:02d}','uncertainty_corners',b2_time_scale=t,b2_power_scale=p,leak_scale=l,wake_energy_J=w)
    assert len(result)==67
    return result

if __name__=='__main__':
    old=ROOT.parent/'study/parameters.json'
    (ROOT/'nominal_synthetic_parameters.json').write_bytes(old.read_bytes())
    cfg={'evidence_class':'SYNTHETIC_UNCALIBRATED_PARAMETER_REGION','temperatures_C':[25+2.5*i for i in range(21)],'nominal_id':'grid_L1_D1_W1','main_horizon_s':.4,'tail_s':10.,'main_step_s':.002,'tail_step_s':.02,'tie_J':1e-7,'investment_threshold_pct':1.,'near_complete_capture_pct':95.,'small_residual_percentage_points':.1,'observation_offsets_C':[-2.,-.5,0.,.5,2.],'hard_scan_seconds':600,'scenarios':scenarios()}
    (ROOT/'design.json').write_text(json.dumps(cfg,indent=2)+'\n',encoding='utf-8')
    files=['PROTOCOL.md','design.py','design.json','nominal_synthetic_parameters.json']
    hashes={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}
    (ROOT/'design_freeze.json').write_text(json.dumps({'stage':'before_first_numerical_scan','previous_results_known':True,'files':hashes},indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'scenarios':len(cfg['scenarios']),'temperatures':len(cfg['temperatures_C']),'copied_old_parameters_sha256':hashes['nominal_synthetic_parameters.json']}))
