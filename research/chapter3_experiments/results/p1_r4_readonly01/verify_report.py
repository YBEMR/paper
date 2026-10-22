"""Check report examples and transcription against saved projections; no production imports."""
import csv
from fractions import Fraction as F
import json
from pathlib import Path
import re

OUT=Path(__file__).resolve().parent


def main():
    read=lambda n:json.loads((OUT/n).read_text(encoding='utf-8'))
    d=read('diagnosis.json');m=read('r4_membership.json')
    with (OUT/'r4_schedules.csv').open(encoding='utf-8-sig',newline='') as stream:s=list(csv.DictReader(stream))
    with (OUT/'r4_response_profiles.csv').open(encoding='utf-8-sig',newline='') as stream:p=list(csv.DictReader(stream))
    checks={}
    for method in ['anchor_linked4','heft']:
        maps={c:{(x['scene'],x['stage_instance']):x['unit'] for x in s if x['condition']==c and x['method']==method} for c in ['P0','P1']}
        checks[method+'/same_own_units_P0_P1']=maps['P0']==maps['P1']
    old=next(x for x in s if x['condition']=='P0' and x['method']=='anchor_linked4' and x['scene']=='AC_offset_0ms' and x['stage']=='C.post')
    new=next(x for x in p if x['condition']=='P1' and x['stage']=='C.post' and x['unit']=='CPU1' and x['opp']=='L')
    checks['P0_Cpost_160_plus_11_52_is_171_52']=F(old['start_ms'])+F(old['duration_ms'])==F('171.52')<=F(old['request_deadline_ms'])
    checks['same_start_P1_Cpost_179_2_exceeds_171_6']=F(old['start_ms'])+F(new['duration_ms'])==F('179.2')>F(old['request_deadline_ms'])
    heft=next(x for x in s if x['condition']=='P1' and x['method']=='heft' and x['scene']=='AC_offset_0ms' and x['stage']=='C.post')
    checks['P1_saved_HEFT_Cpost_150_to_169_2']=F(heft['start_ms'])==150 and F(heft['end_ms_exact'])==F('169.2')<=F(heft['request_deadline_ms'])
    ac=[x for x in s if x['condition']=='P1' and x['method']=='heft' and x['scene']=='AC_offset_0ms']
    checks['P1_saved_HEFT_AC_all_L']=len(ac)==6 and all(x['opp']=='L' for x in ac)
    v=m['P1/phase2/HEFT_ignore_unit']['violations']
    checks['phase2_Cmain_Cpost_excluded_by_OPP_even_ignoring_units']=all(any(x['stage'].endswith('::'+st) and 'closed_opp' in x['causes'] for x in v) for st in ['C.main','C.post'])
    checks['P1_root_not_exhausted']=abs(d['cohorts']['P1']['linked_unused_root_s']-141.422)<1e-6
    checks['P0_near_tie_only_temperature_delta']=all(F(d['cohorts']['P0']['weighted_component_differences_J'][k][0])<=0<=F(d['cohorts']['P0']['weighted_component_differences_J'][k][1]) for k in ['activity','baseline','external_common'])
    text=(OUT/'summary.md').read_text(encoding='utf-8')
    links=re.findall(r'\]\(([^)]+)\)',text)
    checks['all_report_links_exist']=all((OUT/link.split('#')[0]).exists() for link in links)
    checks['P2_not_authorised_or_run']=d['P2_status']['execution_authorised'] is False and d['P2_status']['prepared_or_run'] is False
    output={'passed':all(checks.values()),'count':len(checks),'checks':checks,
        'research_calls':0,'new_thermal_evaluations':0,'scope':'Stored schedules, analytic examples and report links only; not a rerun or new SAFE witness'}
    with (OUT/'report_checks.json').open('x',encoding='utf-8') as stream:
        json.dump(output,stream,ensure_ascii=False,indent=2);stream.write('\n')
    assert output['passed'],[k for k,v in checks.items() if not v]
    print({'passed':True,'checks':len(checks),'new_calls':0})


if __name__=='__main__':main()
