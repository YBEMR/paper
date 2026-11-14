import os
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
import csv,hashlib,json,platform,time
from pathlib import Path
import numpy as np
from model import P,ALL_SEQUENCES,simulate,prefix_idle_energy
import model

ROOT=Path(__file__).resolve().parent;OUT=ROOT/'results';OUT.mkdir(exist_ok=True)
def dump(name,data):
    (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def choice(r,indices):
    ii=np.array(indices,dtype=int);good=ii[r['feasible'][ii]]
    if len(good):return int(good[np.argmin(r['energy'][good])])
    # Deterministic failed-plan fallback, never counted as feasible savings.
    return int(min(ii,key=lambda i:(r['deadline_misses'][i],r['unfinished_work'][i],r['energy'][i],i)))
def record(name,r,i,seq):
    return {'method':name,'sequence_indices':list(map(int,seq)),'sequence':[P['templates'][int(a)]['id'] for a in seq],'feasible':bool(r['feasible'][i]),'complete_tasks':int(r['completed'][i]),'deadline_misses':int(r['deadline_misses'][i]),'unfinished_work':float(r['unfinished_work'][i]),'energy':float(r['energy'][i]),'main_energy':float(r['main_energy'][i]),'tail_energy':float(r['tail_energy'][i]),'peak':r['peak'][i].tolist(),'hardware_entries':r['hw_entries'][i].tolist(),'capped_busy_time':r['cap_busy_time'][i].tolist(),'frequency_changes':r['frequency_changes'][i].tolist(),'start':[None if np.isnan(v) else float(v) for v in r['start'][i]],'finish':[None if np.isnan(v) else float(v) for v in r['finish'][i]],'components':r['components'][i].tolist()}
def main():
    start=time.monotonic();freeze=json.loads((ROOT/'design_freeze.json').read_text());assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==v for n,v in freeze['files'].items())
    model.DEADLINE=start+P['scan_budget_seconds']
    fixed=np.where(np.all(ALL_SEQUENCES==ALL_SEQUENCES[:,0,None],axis=1))[0]
    low=[i for i in fixed if P['templates'][int(ALL_SEQUENCES[i,0])]['frequency']==[.5,.5]]
    cold=simulate(P['scenarios'][1],ALL_SEQUENCES[fixed],hardware=False,cold_table=True,prefix=False)
    cold_row=choice(cold,np.arange(16));cold_index=int(fixed[cold_row]);cold_seq=ALL_SEQUENCES[cold_index];dump('cold_table_selection.json',{'selection':record('cold_table_only',cold,cold_row,cold_seq),'all_fixed_energy':cold['energy'].tolist(),'all_fixed_feasible':cold['feasible'].tolist()})
    summaries=[];methods=[];store_arrays={};counterfactual=[]
    with (OUT/'all_candidates.csv').open('w',newline='',encoding='utf-8') as file:
        fields=['scenario','hardware_enabled','sequence_index','template0','template1','template2','feasible','completed','deadline_misses','unfinished_work','energy','main_energy','tail_energy','peak_X','peak_Y','trips_X','trips_Y','capped_busy_X','capped_busy_Y','switches_X','switches_Y'];w=csv.DictWriter(file,fieldnames=fields);w.writeheader()
        for ci,s in enumerate(P['scenarios']):
            if time.monotonic()-start>P['scan_budget_seconds']:raise TimeoutError('Frozen scan budget exceeded; preserve completed outputs')
            r=simulate(s,ALL_SEQUENCES)
            pred=prefix_idle_energy(s,r['prefix']);eligible=r['prefix']['first8_feasible']
            prefix_i=int(np.argmin(np.where(eligible,pred,np.inf))) if eligible.any() else choice(r,np.arange(len(ALL_SEQUENCES)))
            first=int(ALL_SEQUENCES[prefix_i,0]);mpc=choice(r,np.where(ALL_SEQUENCES[:,0]==first)[0]);oracle=choice(r,np.arange(len(ALL_SEQUENCES)));bestfixed=choice(r,fixed);safelow=choice(r,low)
            react=simulate(s,[cold_seq],reactive=True,prefix=False)
            selected=[record('cold_fixed_plus_hardware',r,cold_index,cold_seq),record('safe_low_fixed',r,safelow,ALL_SEQUENCES[safelow]),record('reactive_threshold',react,0,cold_seq),record('two_period_lookahead',r,mpc,ALL_SEQUENCES[mpc]),record('catalogue_best',r,oracle,ALL_SEQUENCES[oracle]),record('best_thermal_fixed',r,bestfixed,ALL_SEQUENCES[bestfixed])]
            for x in selected:x['scenario']=s['id']
            methods.extend(selected)
            simple=[x for x in selected if x['method'] in ['cold_fixed_plus_hardware','safe_low_fixed','reactive_threshold','best_thermal_fixed'] and x['feasible']]
            base=min(simple,key=lambda x:x['energy']) if simple else None
            # Reactive can use within-task software caps outside the 4096-template
            # catalogue. Therefore the catalogue reference is not a lower bound
            # on reactive energy; the comparison preserves a negative gap.
            def gain(k):return 100*(base['energy']-selected[k]['energy'])/base['energy'] if base and selected[k]['feasible'] else None
            summaries.append({'scenario':s['id'],'feasible_catalogue':int(r['feasible'].sum()),'any_hardware_trip_candidates':int((r['hw_entries'].sum(axis=1)>0).sum()),'active_cap_candidates':int((r['cap_busy_time'].sum(axis=1)>1e-9).sum()),'strong_simple':base['method'] if base else None,'strong_simple_energy':base['energy'] if base else None,'lookahead_gain_pct':gain(3),'catalogue_gain_pct':gain(4),'lookahead_extra_energy_budget_for_1pct':.99*base['energy']-selected[3]['energy'] if base and selected[3]['feasible'] else None,'catalogue_extra_energy_budget_for_1pct':.99*base['energy']-selected[4]['energy'] if base and selected[4]['feasible'] else None,'lookahead_feasible':selected[3]['feasible'],'catalogue_feasible':selected[4]['feasible'],'cold_fixed_feasible':selected[0]['feasible'],'low_fixed_feasible':selected[1]['feasible'],'reactive_feasible':selected[2]['feasible'],'best_fixed_feasible':selected[5]['feasible'],'lookahead_sequence':selected[3]['sequence_indices'],'catalogue_sequence':selected[4]['sequence_indices'],'best_fixed_sequence':selected[5]['sequence_indices'],'prefix_lookahead_feasible':bool(eligible.any())})
            variants=[(True,r)]
            if s['id'] in P['counterfactual_scenarios']:
                no=simulate(s,ALL_SEQUENCES,hardware=False,prefix=False);oi=choice(no,np.arange(len(ALL_SEQUENCES)));fi=choice(no,fixed)
                counterfactual.append({'scenario':s['id'],'no_hardware_best':record('no_hardware_catalogue',no,oi,ALL_SEQUENCES[oi]),'no_hardware_best_fixed':record('no_hardware_fixed',no,fi,ALL_SEQUENCES[fi]),'hardware_best_replayed_without_cap':record('same_hardware_winner_no_cap',no,oracle,ALL_SEQUENCES[oracle]),'no_cap_winner_replayed_with_hardware':record('same_no_cap_winner_with_cap',r,oi,ALL_SEQUENCES[oi]),'no_hardware_winner_index':oi,'hardware_winner_index':oracle});variants.append((False,no))
            for hw,data in variants:
                key=s['id']+('_hardware' if hw else '_no_cap')
                for name in ['energy','main_energy','feasible','completed','deadline_misses','unfinished_work','peak','hw_entries','cap_busy_time','start','finish','components','frequency_changes']:store_arrays[key+'__'+name]=data[name]
                for i,seq in enumerate(ALL_SEQUENCES):w.writerow(dict(zip(fields,[s['id'],hw,i,*seq,bool(data['feasible'][i]),int(data['completed'][i]),int(data['deadline_misses'][i]),data['unfinished_work'][i],data['energy'][i],data['main_energy'][i],data['tail_energy'][i],*data['peak'][i],*data['hw_entries'][i],*data['cap_busy_time'][i],*data['frequency_changes'][i]])))
            dump('scenario_summary.json',summaries);dump('selected_methods.json',methods);dump('counterfactual.json',counterfactual)
            print(json.dumps({'scenario':s['id'],'elapsed_s':round(time.monotonic()-start,2),'feasible':summaries[-1]['feasible_catalogue'],'trip_candidates':summaries[-1]['any_hardware_trip_candidates'],'lookahead_gain_pct':summaries[-1]['lookahead_gain_pct'],'catalogue_gain_pct':summaries[-1]['catalogue_gain_pct']}),flush=True)
    np.savez_compressed(OUT/'all_candidate_arrays.npz',sequences=ALL_SEQUENCES,**store_arrays)
    with (OUT/'scenario_summary.csv').open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=list(summaries[0]));w.writeheader();w.writerows(summaries)
    meta={'status':'COMPLETE','python':platform.python_version(),'numpy':np.__version__,'elapsed_s':time.monotonic()-start,'hardware_cases':13,'counterfactual_cases':2,'sequences_per_case':4096,'finite_candidate_evaluations':15*4096,'reactive_executions':13,'cold_table_fixed_executions':16,'files_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['PROTOCOL.md','design.json','model.py','run_experiment.py']}}
    dump('run_environment.json',meta);print(json.dumps(meta),flush=True)

if __name__=='__main__':main()
