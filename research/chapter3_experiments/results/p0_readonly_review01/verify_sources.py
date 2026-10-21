"""Verify used archived bytes and locate frozen domain rules; no production imports."""
import ast
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
REPO = next(p for p in OUT.parents if (p/'AGENTS.md').is_file())
ROOT = REPO/'research/chapter3_experiments'
read = lambda p: json.loads(p.read_text(encoding='utf-8'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    diagnosis = read(OUT/'diagnosis.json')
    archived = {r['path']: r['sha256'] for r in read(ROOT/'results/p0_resume01/archive_inventory.json')['files']}
    frozen = read(ROOT/'results/p0_resume01/declaration.json')['source_sha256']
    checks = {}
    for path, digest in diagnosis['source_sha256'].items():
        checks[path+'/current_bytes'] = sha(REPO/path) == digest
        if path in archived:
            checks[path+'/original_archive'] = digest == archived[path]
        elif path in frozen:
            checks[path+'/frozen_source'] = digest == frozen[path]
        else:
            raise ValueError('Used source lacks original binding: '+path)
    locators = []
    requested = {'linked_neighborhood.py': ['_member'],
                 'run_neighborhood_diagnostic.py': ['opened_stages'],
                 'run_four_method_comparison.py': ['masks', 'settings'],
                 'p0_batch/run_p0.py': ['fresh_input', 'jobs'],
                 'linked_method.py': ['execute_linked_fixed_unit_opp_start']}
    for name, functions in requested.items():
        path = ROOT/name; relative = path.relative_to(REPO).as_posix()
        checks[relative+'/frozen_rule_bytes'] = sha(path) == frozen[relative]
        nodes = {n.name:n for n in ast.parse(path.read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef)}
        for function in functions:
            n = nodes[function]
            locators.append({'path':relative,'function':function,'start_line':n.lineno,'end_line':n.end_lineno,'sha256':sha(path)})
    result = {'passed':all(checks.values()),'count':len(checks),'checks':checks,'code_locators':locators,
              'research_calls':0,'new_thermal_evaluations':0,'scientific_sources_modified':False,
              'scope':'Used evidence matches original K156 archive/freeze; structural source read, no numerical rerun'}
    with (OUT/'source_checks.json').open('x',encoding='utf-8') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
    assert result['passed'],[k for k,v in checks.items() if not v]
    print({'passed':True,'source_checks':len(checks),'code_locators':len(locators)})

if __name__=='__main__':main()
