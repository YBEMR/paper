"""K152 final provenance and link check. No research or physical evaluation."""
from pathlib import Path
import sys,json,re
HERE=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(HERE))
import run_four_method_comparison as r
out=r.TARGET;d=r.admission(out)
review=r.read(out/'independent_review.json');facts=r.read(out/'analysis01/facts.json')
checks={
 'admission_frozen_178':len(d['source_sha256'])==178,
 'independent_83_passed':review['passed'] and review['check_count']==83,
 'ledger_completed_4':r.read(out/'ledger.json')['state']=='COMPLETED' and r.read(out/'ledger.json')['consumed']==4,
 'no_watchdog':r.read(out/'launcher_result.json')['outer_watchdog_stopped'] is False,
 'SA_L0_explicit_time':facts['methods'][-1]['L0']['formed_at_s']==r.read(out/'sa101/result.json')['lower_bound_formed_at_s'],
 'old_analysis_preserved':(out/'analysis01_before_L0_fix/facts.json').is_file(),
 'old_analysis_source_matches':r.sha(Path(__file__).with_name('analyze_before_L0_fix.py'))==r.read(out/'analysis01_before_L0_fix/integrity_checks.json')['analysis_script_sha256'],
 'actual_method_time':abs(sum(r.read(out/j['id']/'result.json')['timing']['method_elapsed_s'] for j in r.jobs())-917.391)<1e-6,
}
for n,q in enumerate([out/'summary.md',out/'analysis01/summary.md',out/'independent_review.md']):
 bad=[]
 for url in re.findall(r'\]\(([^)]+)\)',q.read_text(encoding='utf-8')):
  if not(url.startswith(('http','/','#')) or (q.parent/url.split('#')[0]).exists()):bad.append(url)
 checks['links_'+str(n)]=not bad
for name,h in r.read(out/'analysis01/integrity_checks.json')['after_sha256'].items():
 if r.sha(r.REPO/name)!=h:raise ValueError('Raw changed: '+name)
checks['analysis_340_raw_files_still_unchanged']=True
print(json.dumps(checks,ensure_ascii=False))
if not all(checks.values()):raise SystemExit(1)
with (out/'delivery_verification.json').open('x',encoding='utf-8') as f:
 json.dump({'passed':True,'checks':checks,'source_count':178,'new_research_calls':0,
  'new_models':0,'new_physical_evaluations':0,'scope':'final provenance and links only',
  'script_sha256':r.sha(__file__),'at_utc':r.now()},f,ensure_ascii=False,indent=2)
