"""Saved-result and hash checks only. No solver, schedules, or thermal simulation."""
from pathlib import Path
import csv, json, hashlib, math, sys, collections
ROOT=Path(__file__).resolve().parents[2]
RUN=Path(sys.argv[1]).resolve()
def js(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def csvs(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def num(x):return float(x)
rules=js(ROOT/'research/pressure78_design/rules_v1.json')
inputs=js(ROOT/'research/pressure78_design/inputs_v1.json')
rows=csvs(RUN/'summary.csv');checks=csvs(RUN/'postchecks.csv')
assert len(rows)==len(checks)==66
assert len({r['call_index'] for r in rows})==66
for r,z in zip(rows,rules['calls']):
    assert int(r['call_index'])==z['call_index']
    assert int(r['trial_index'])==z['trial_index']
    assert int(r['rep'])==z['repeat'] and r['method']==z['method']
    case=inputs['cases'][z['trial_index']-1]
    assert r['case_id']==case['id'] and r['base_id']==case['base_id']
    assert num(r['initial_C'])==case['initial_C'][0]
    assert r['raw_method_status']!='error'
    assert r['independent_infeasible']=='0'  # neither solver exports integer infeasibility certificates
    detail=js(RUN/f"diagnostics_call_{int(r['call_index']):03d}.json")
    if r['safe']=='1':
        assert math.isfinite(num(r['energy_mJ']))
        assert 0<=num(r['first_safe_s'])<=num(r['first_safe_upper_s'])<=60
        assert r['budget_evidence_ambiguous']=='0'
    assert all(e['origin']!='injected_duplicate' for e in detail['events'])
    assert all(not rd['output'].get('test_only_replay',False) for rd in detail['rounds'])
    keys={tuple(sorted(e['selected'])) for e in detail['events']}
    assert len(keys)==int(r['distinct_candidates'])
    assert len(detail['cuts'])==int(r['cuts'])
    if r['method']=='thermal_row':
        assert sum(c['kind']=='temperature_row' for c in detail['cuts'])==int(r['thermal_rows'])
        for c in detail['cuts']:
            if c['kind']=='temperature_row':
                assert c['reason']=='certified_fixed_time'
    check=checks[int(r['call_index'])-1]
    assert (check['checked']=='1')==(r['safe']=='1')
    if check['checked']=='1':assert check['passed']=='1'
protected=js(ROOT/'research/pressure78_design/protected_before.json')
changes=[x['path'] for x in protected if not (ROOT/x['path']).is_file() or sha(ROOT/x['path'])!=x['sha256'].lower()]
# Preserve concurrent non-method changes rather than overwrite user artifacts.
# Any changed experimental source/input/result or LaTeX source remains fatal.
latex_build_files={f'research/latex/main{e}' for e in ['.aux','.fdb_latexmk','.fls','.log','.pdf','.synctex.gz']}
critical_changes=[p for p in changes if p not in latex_build_files]
assert not critical_changes,critical_changes
changed_details=[]
for x in protected:
    if x['path'] in changes:
        p=ROOT/x['path']
        changed_details.append(dict(path=x['path'],before=x['sha256'],after=sha(p) if p.is_file() else None,
                                    scope='concurrent LaTeX build artifact; not written or reverted by this task'))
hashes=js(RUN/'source_hashes.json')
for i,x in enumerate(hashes,1):
    p=Path(x['path']);snap=RUN/'source'/f"{i:03d}_{p.name}"
    assert sha(snap)==x['sha256'].lower()
    assert sha(p)==x['sha256'].lower()
groups={}
for cohort in ['diagnostic','main']:
    groups[cohort]={}
    for method in ['no_good','thermal_row']:
        rr=[r for r in rows if r['cohort']==cohort and r['method']==method]
        groups[cohort][method]=dict(calls=len(rr),safe=sum(r['safe']=='1' for r in rr),
            independent_optimal=sum(r['independent_optimal']=='1' for r in rr),
            statuses=dict(collections.Counter(r['status'] for r in rr)),
            first_candidate_states=dict(collections.Counter(r['first_distinct_candidate_thermal_status'] for r in rr)),
            rounds=sum(int(r['rounds']) for r in rr),thermal_calls=sum(int(r['thermal_calls']) for r in rr),
            thermal_rows=sum(int(r['thermal_rows']) for r in rr),no_goods=sum(int(r['no_goods']) for r in rr),
            distinct_candidates=sum(int(r['distinct_candidates']) for r in rr),
            elapsed_total_s=sum(num(r['elapsed_s']) for r in rr))
paired=[]
for i in range(2,18):
    rs=[r for r in rows if int(r['trial_index'])==i]
    out=dict(case_id=rs[0]['case_id'],initial_C=num(rs[0]['initial_C']),methods={})
    for method in ['no_good','thermal_row']:
        rr=sorted([r for r in rs if r['method']==method],key=lambda r:int(r['rep']))
        out['methods'][method]={k:[r[k] for r in rr] for k in
             ['status','safe','energy_mJ','first_safe_s','first_safe_upper_s','elapsed_s','rounds','cuts','thermal_rows','no_goods']}
    paired.append(out)
# Only historical consistency checks AFTER completion, never a solver input.
old=csvs(ROOT/'research/matlab_config_value_src/feedback77_reports/frozen_20260928_172132_129/summary.csv')
old={(r['case_id'],r['method']):r for r in old}
historical_differences=[]
for r in rows:
    if r['cohort']=='main' and num(r['initial_C'])==78:
        o=old[(r['base_id'],r['method'])]
        for key in ['energy_mJ','status','independent_optimal']:
            if r[key]!=o[key]:historical_differences.append(dict(call=r['call_index'],field=key,old=o[key],new=r[key]))
result=dict(calls=66,protected_files=len(protected),protected_unchanged=len(protected)-len(changes),
            protected_changes=changes,changed_details=changed_details,critical_changes=critical_changes,
            source_snapshot_count=len(hashes),source_unchanged=True,groups=groups,
            paired_main=paired,historical_78C_differences=historical_differences)
(RUN/'postcheck_readonly.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='paired_main'},ensure_ascii=False,indent=2))
