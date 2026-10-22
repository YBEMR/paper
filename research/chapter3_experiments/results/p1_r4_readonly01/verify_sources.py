"""Check used evidence against original archives/freeze, without production imports."""
import ast
import hashlib
import json
from pathlib import Path

OUT=Path(__file__).resolve().parent
REPO=next(p for p in OUT.parents if (p/'AGENTS.md').is_file())
EXP=REPO/'research/chapter3_experiments'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    d=read(OUT/'diagnosis.json');checks={};archives={}
    for folder in ['p0_resume01','p1_execution01']:
        archives.update({r['path']:r['sha256'] for r in read(EXP/'results'/folder/'archive_inventory.json')['files']})
    frozen=read(EXP/'results/p1_execution01/declaration.json')['source_sha256']
    for name,h in d['source_sha256'].items():
        checks[name+'/unchanged']=sha(REPO/name)==h
        expected=archives.get(name,frozen.get(name))
        if expected is None:raise ValueError('Used source has no original archive/freeze binding: '+name)
        checks[name+'/original_binding']=h==expected
    rules={'linked_neighborhood.py':['_member','make_linked_condition'],
        'neighborhood.py':['_member'],'run_four_method_comparison.py':['masks'],
        'run_neighborhood_diagnostic.py':['opened_stages'],
        'linked_method.py':['execute_linked_fixed_unit_opp_start'],
        'neighborhood_method.py':['execute_n1_neighborhood'],
        'inputs.py':['_build_modes']}
    locators=[]
    for name,funcs in rules.items():
        p=EXP/name;relative=p.relative_to(REPO).as_posix()
        checks[relative+'/frozen']=sha(p)==frozen[relative]
        nodes={n.name:n for n in ast.parse(p.read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef)}
        for fn in funcs:
            if fn not in nodes:continue
            n=nodes[fn];locators.append({'path':relative,'function':fn,'start_line':n.lineno,'end_line':n.end_lineno,'sha256':sha(p)})
    script=ast.parse((OUT/'analyze.py').read_text(encoding='utf-8'))
    imports=[n.module for n in ast.walk(script) if isinstance(n,ast.ImportFrom)]
    imports+=[a.name for n in ast.walk(script) if isinstance(n,ast.Import) for a in n.names]
    checks['analysis_imports_only_stdlib']=set(imports)<= {'collections','csv','fractions','hashlib','json','pathlib'}
    checks['all_211_frozen_scientific_and_execution_sources_unchanged']=all(sha(REPO/name)==h for name,h in frozen.items())
    result={'passed':all(checks.values()),'count':len(checks),'checks':checks,'code_locators':locators,
        'research_calls':0,'new_thermal_evaluations':0,'algorithm_or_inputs_modified':False,
        'origin':'same-chat stored-evidence verification, not external approval or rerun'}
    with (OUT/'source_checks.json').open('x',encoding='utf-8') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
    assert result['passed'],[k for k,v in checks.items() if not v]
    print({'passed':True,'checks':len(checks),'locators':len(locators),'new_calls':0})


if __name__=='__main__':main()
