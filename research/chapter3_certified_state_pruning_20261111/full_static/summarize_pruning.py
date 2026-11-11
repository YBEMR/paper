"""Summarize completed production certificate records only."""
from fractions import Fraction as F
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent

def main():
    data=json.loads((HERE/'execution/on/preprocessing.json').read_text())['joint_state_pruning']
    scenes={};all_slack=[];all_margins=[]
    for sid,scene in data['scenes'].items():
        intervals=scene['interval_reports']
        slack=[F(st['minimum_slack']) for row in intervals
               for st in row['gate_off_audit'].get('states',[])]
        margins=[F(p['strict_margin']) for p in scene['certificate_catalogue'].values()
                 if p['rule']=='exported_dependency_path']
        assert all(p['exceeds_path_row_tolerance'] for p in scene['certificate_catalogue'].values()
                   if p['rule']=='exported_dependency_path')
        scenes[sid]=dict(candidates=sum(r['candidate_count'] for r in intervals),
            retained=sum(r['retained_count'] for r in intervals),
            removed=sum(r['deleted_count'] for r in intervals),
            gate_off_rows_checked=sum(r['gate_off_audit']['rows_checked'] for r in intervals),
            gate_off_minimum_slack_exact=str(min(slack)),
            unique_dependency_certificates=len(margins),minimum_dependency_margin_exact=str(min(margins)),
            support_preparation_s=scene['preparation_elapsed_s'],
            support_interval_sum_s=sum(r['elapsed_s'] for r in intervals))
        all_slack+=slack;all_margins+=margins
    result=dict(per_scene=scenes,gate_off_rows_checked=sum(s['gate_off_rows_checked'] for s in scenes.values()),
        gate_off_minimum_slack_exact=str(min(all_slack)),gate_off_minimum_slack=float(min(all_slack)),
        minimum_dependency_margin_exact=str(min(all_margins)),minimum_dependency_margin=float(min(all_margins)),
        all_recorded_dependency_margins_exceed_1e_9_per_row=True,
        scope='Read completed production certificate reports only; no build or solver calls',
        new_model_builds=0,new_solver_calls=0,new_thermal_calls=0)
    with (HERE/'pruning_audit_summary.json').open('x') as stream:json.dump(result,stream,indent=2)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
