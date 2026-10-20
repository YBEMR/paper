"""K141 read-only source/provenance audit; no production imports or evaluation."""
from pathlib import Path
import argparse
import hashlib
import json

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'AGENTS.md').is_file())
HERE=ROOT/'research/chapter3_experiments'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def audit():
    old_path=HERE/'results/night_k127_run02/declaration.json'
    current_path=HERE/'results/linked_quality_pair01/declaration.json'
    old,current=read(old_path),read(current_path)
    changes=[p for p,h in old['source_sha256'].items() if sha(ROOT/p)!=h]
    expected=['research/chapter3_experiments/'+n for n in
              ['matlab_bridge.py','milp.py','neighborhood_method.py']]
    assert len(old['source_sha256'])==125 and set(changes)==set(expected)
    assert len(current['source_sha256'])==157
    assert all(sha(ROOT/p)==h for p,h in current['source_sha256'].items())
    chains=[]
    for name,gate_name,count in [
        ('matlab_bridge.py','runtime_io_precheck02',129),
        ('milp.py','linked_precheck02',66),
        ('neighborhood_method.py','linked_precheck02',66)]:
        gate_path=HERE/'results'/gate_name/'checks.json'; gate=read(gate_path)
        key='research/chapter3_experiments/'+name
        assert gate['passed'] is True and gate.get('count',gate.get('tests_run'))==count
        assert gate['source_sha256'][key]==sha(ROOT/key)==current['source_sha256'][key]
        chains.append({'source':key,'sha256':sha(ROOT/key),'gate':gate_path.relative_to(ROOT).as_posix(),
                       'gate_sha256':sha(gate_path),'passed':True,'count':count})
    unchanged={p:h for p,h in old['source_sha256'].items() if p not in expected}
    dependencies=[
        'formal_milp.py','run_warm_diagnostic.py','initial_point.py','method_runner.py',
        'heuristic_runner.py','heft_method.py','sa_method.py','heuristic_common.py',
        'auto_heuristic_policy.py','thermal.py','schedules.py','control_policy.py',
        'inputs.py','config_v01.json','solve_model.m','partial_bounds.py']
    for name in dependencies:
        key='research/chapter3_experiments/'+name
        assert unchanged[key]==current['source_sha256'][key]==sha(ROOT/key)
    old_gate=HERE/'results/night_k127_run02/targeted_checks.json'
    g=read(old_gate)
    assert g['passed'] and g['count']==67
    wrapper=HERE/'results/linked_pair_wrapper_precheck02/checks.json'
    assert read(wrapper)['passed'] and read(wrapper)['tests_run']==28
    default_fixture=HERE/'results/linked_precheck02/fixture_records.json'
    fixture=read(default_fixture)
    return {'stage':'K141','scope':'code identity and inherited evidence; not a new performance or physical experiment',
        'passed':True,'old_source_count':125,'old_unchanged_count':len(unchanged),
        'old_changed_source_count':len(changes),'old_changed_sources':changes,
        'K140_source_count':157,'K140_sources_unchanged':True,
        'old_declaration':{'path':old_path.relative_to(ROOT).as_posix(),'sha256':sha(old_path)},
        'K140_declaration':{'path':current_path.relative_to(ROOT).as_posix(),'sha256':sha(current_path)},
        'old_67_gate':{'path':old_gate.relative_to(ROOT).as_posix(),'sha256':sha(old_gate),'count':67,
                      'interpretation':'historical gate; unchanged modules inherited by hash, not all125 current-match'},
        'changed_source_current_evidence':chains,
        'default_regression_fixture':{'path':default_fixture.relative_to(ROOT).as_posix(),
            'sha256':sha(default_fixture),'top_level_keys':list(fixture),
            'scope':'K139 default/N1/all eight-array regression only; no native full-scale proof'},
        'unchanged_dependencies':{p:unchanged['research/chapter3_experiments/'+p] for p in dependencies},
        'no_need_to_change_candidate_or_physical_rules':True,'new_test_runs':0,'new_model_or_heat_evaluations':0,
        'new_native_or_research_calls':0,'no_current_whole_67_matching_claim':True}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(); result=audit()
    args.out.resolve().relative_to(ROOT)
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['passed','old_source_count','old_unchanged_count','old_changed_sources','K140_sources_unchanged']},ensure_ascii=False))
