"""Read the completed frozen eight-arm batch. No new scientific calls."""
import csv
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

OUT=Path(__file__).resolve().parent
REPO=next(p for p in OUT.parents if (p/'RESEARCH_BRIEF.md').is_file())
EX=OUT/'execution'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
save=lambda n,v:(OUT/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def main():
    batch=read(EX/'batch_return.json');plan=read(EX/'plan.json');summary=read(EX/'summary.json')
    assert batch['all_planned_method_slots_returned'] and batch['stop_reason'] is None
    assert batch['retry_count']==0 and len(summary['rows'])==8
    for n,h in plan['source_sha256'].items():assert sha(REPO/n)==h and sha(EX/'source_snapshot'/n)==h
    for n,h in plan['input_file_sha256'].items():assert sha(EX/n)==h
    old=REPO/'research/chapter4_scheduler/results/scale24_i1_20261113'
    oldfiles=read(old/'files_sha256.json')
    for n,h in oldfiles.items():assert sha(REPO/n)==h
    details={};curves=[];rows=[]
    for row in summary['rows']:
        sid=row['id'];folder=EX/'calls'/sid;raw=read(folder/'method/result.json');ret=read(folder/'method_return.json')
        post=read(folder/'post_return.json');construct=read(folder/'method/construction_statistics.json')
        assert sha(folder/'method/result.json')==ret['raw_result_sha256']
        assert raw['initialization_version']=='I1'
        assert row['safe'] and post['passed'] and post['same_numerical_evaluator']
        assert raw['evaluation']['completed_at_elapsed_s']<300
        for e in raw['evaluations']:
            if e['phase']=='initialization':assert e['evaluation_admitted_at_s']<180
            if e.get('incumbent_replaced'):assert e['receipt']['completed_at_elapsed_s']<300
        before=raw['initial_safe_snapshot']
        byhash={e['candidate_sha256']:e for e in raw['evaluations']}
        for p in raw['graph_proposals']:
            if not p['strict_accepted']:continue
            ev=byhash[p['candidate_sha256']]
            assert F(ev['receipt']['weighted_energy_J'][1])<F(before['receipt']['weighted_energy_J'][0])
            before=ev
        assert before['candidate']==raw['safe_candidate']
        physical=[e for e in raw['evaluations'] if not e.get('cache_hit',False)]
        returned=[a for a in ret['evaluation_attempts_journal'] if a['state']=='RETURNED']
        assert len(physical)==len(returned)
        initial=[];search=[]
        for e,j in zip(physical,returned):
            assert e['candidate_sha256']==j['candidate_sha256']
            item={'sha256':e['candidate_sha256'],'energy':e['receipt'].get('weighted_energy_J'),
                'state':e['receipt']['state'],'evaluation_s':j['returned_at_s']-j['started_at_s']}
            (initial if e['phase']=='initialization' else search).append(item)
        handoff=row['initialization_completed_at_s']
        search_eval=sum(p['exclusive_s'] for p in raw['timing']['phase_records']
            if p['phase']=='complete_continuous_evaluation' and p['start_s']>=handoff)
        other=row['search_s']-search_eval-row['graph_construction_s']-row['prefilter_total_s']
        assert other>=-1e-6
        rr={**row,'search_evaluation_s':search_eval,'search_other_s':max(0,other),
            'actual_total_construction_calls':row['actual_base_calls']+row['actual_extra_calls'],
            'search_structure_plus_filter_s':row['graph_construction_s']+row['prefilter_total_s'],
            'first_SAFE_at_s':raw['first_safe_at_s']}
        rows.append(rr)
        sequence=[p['candidate_sha256'] for p in raw['graph_proposals']]
        details[sid]={'initial_candidate_sha256':raw['initial_safe_snapshot']['candidate_sha256'],
            'initial_energy':raw['initial_safe_snapshot']['receipt']['weighted_energy_J'],
            'initial_evaluations':initial,'search_evaluations':search,'proposal_sequence':sequence,
            'accepted_sequence':[p['candidate_sha256'] for p in raw['graph_proposals'] if p['strict_accepted']],
            'construction_observer':construct,
            'prefilter_counts':read(folder/'method/prefilter.json')['counts'] if (folder/'method/prefilter.json').exists() else {}}
        for e in raw['events']:
            curves.append({'slot':sid,'case_id':row['case_id'],'arm':row['arm'],
                'time_s':e['at_s'],'phase':e['phase'],'energy_J':float(F(e['energy']['upper'])),
                'candidate_sha256':e['candidate_sha256']})
    comparisons=[]
    for case in ('U03__n24','U04__n24'):
        arms={r['arm']:r for r in rows if r['case_id']==case}
        for a,b in (('ON_P','ON'),('OFF_P','OFF'),('ON','OFF'),('ON_P','OFF_P')):
            x,y=arms[a],arms[b];dx,dy=details[x['id']],details[y['id']]
            ix,iy=dx['initial_evaluations'],dy['initial_evaluations']
            n=next((i for i,(u,v) in enumerate(zip(ix,iy)) if u['sha256']!=v['sha256']),min(len(ix),len(iy)))
            assert all(u['energy']==v['energy'] for u,v in zip(ix[:n],iy[:n]))
            same=dx['initial_candidate_sha256']==dy['initial_candidate_sha256'] and dx['initial_energy']==dy['initial_energy']
            same_seq=n==len(ix)==len(iy)
            sx,sy=dx['proposal_sequence'],dy['proposal_sequence'];k=min(len(sx),len(sy));prefix=sx[:k]==sy[:k]
            if (a,b) in (('ON_P','ON'),('OFF_P','OFF')) and same and same_seq:assert prefix
            comparisons.append({'case_id':case,'arm':a,'reference':b,'same_initial':same,
                'same_initial_sequence':same_seq,'identical_initial_prefix':n,
                'common_prefix_arm_eval_s':sum(e['evaluation_s'] for e in ix[:n]),
                'common_prefix_reference_eval_s':sum(e['evaluation_s'] for e in iy[:n]),
                'common_proposal_prefix_equal':prefix,'common_proposal_prefix_checked':k,
                'strict_final_interval_improvement':F(x['energy_upper_J'])<F(y['energy_lower_J']),
                'observed_energy_saving_percent':(y['energy_J']-x['energy_J'])/y['energy_J']*100,
                'observed_construction_call_difference':x['actual_total_construction_calls']-y['actual_total_construction_calls'],
                'observed_structure_plus_filter_time_difference_s':x['search_structure_plus_filter_s']-y['search_structure_plus_filter_s']})
    save('analysis.json',{'source_commit':plan['subject_commit'],'rows':rows,'comparisons':comparisons,
        'details':details,'real_new_calls_in_analysis':0,'original_archive_files_unchanged':len(oldfiles),
        'frozen_source_files_unchanged':len(plan['source_sha256']),'all_final_and_post_SAFE':True,
        'all_accepted_receipts_within_budget':True,'all_initial_evaluations_admitted_before_180':True,
        'strict_acceptance_verified':True,'scope':'Development regression; same evaluator post, not independent numerical implementation.'})
    for name,data in [('all_metrics.csv',rows),('energy_time.csv',curves),('comparisons.csv',comparisons)]:
        with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in data for k in r)));w.writeheader();w.writerows(data)
    plot(rows,curves)
    print(json.dumps({'successes':len(rows),'comparisons':comparisons},ensure_ascii=False,indent=2))


def plot(rows,curves):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Sans','svg.fonttype':'none','font.size':10})
    colors={'ON':'#b5473b','ON_P':'#7f1722','OFF':'#499bbd','OFF_P':'#155d83'}
    order=['ON','ON_P','OFF','OFF_P']
    fig,axes=plt.subplots(1,2,figsize=(11,4.2),layout='constrained')
    for ax,case in zip(axes,('U03__n24','U04__n24')):
        visible=[]
        for arm in order:
            points=[p for p in curves if p['case_id']==case and p['arm']==arm]
            visible.extend(p['energy_J'] for p in points if p['time_s']>=175)
            prior=[p for p in points if p['time_s']<175]
            if prior:visible.append(prior[-1]['energy_J'])
            ax.step([p['time_s'] for p in points]+[300],[p['energy_J'] for p in points]+[points[-1]['energy_J']],
                where='post',label=arm.replace('_','-'),color=colors[arm],linestyle='--' if arm.endswith('_P') else '-',linewidth=1.7)
        ax.set_title(case.replace('__n',' / ')+' Stage');ax.set_xlim(175,300);ax.grid(alpha=.2)
        pad=(max(visible)-min(visible))*.06
        ax.set_ylim(min(visible)-pad,max(visible)+pad)
        ax.set_xlabel('Method elapsed time (s)');ax.set_ylabel('Accepted SAFE energy upper bound (J)');ax.legend()
    fig.savefig(OUT/'energy_search.png',dpi=180);fig.savefig(OUT/'energy_search.svg');plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11,4),layout='constrained')
    layers=[('initialization_completed_at_s','I1 + setup','#c8c8c8'),('search_evaluation_s','Search evaluation','#82b2c9'),
        ('graph_construction_s','Construction','#dc9d67'),('prefilter_total_s','Prefilter','#876ca6'),('search_other_s','Other','#6c777f')]
    for ax,case in zip(axes,('U03__n24','U04__n24')):
        selected=[next(r for r in rows if r['case_id']==case and r['arm']==arm) for arm in order]
        left=[0.0]*4
        for key,label,color in layers:
            values=[r[key] for r in selected];ax.barh(range(4),values,left=left,label=label,color=color)
            left=[a+b for a,b in zip(left,values)]
        ax.set_yticks(range(4),[a.replace('_','-') for a in order]);ax.invert_yaxis();ax.set_xlim(0,310)
        ax.set_title(case.replace('__n',' / ')+' Stage');ax.set_xlabel('Recorded wall time (s)')
    handles,labels=axes[0].get_legend_handles_labels();fig.legend(handles,labels,loc='outside lower center',ncol=5,fontsize=9)
    fig.savefig(OUT/'cost_breakdown.png',dpi=180);fig.savefig(OUT/'cost_breakdown.svg');plt.close(fig)
    for f in OUT.glob('*.svg'):f.write_text('\n'.join(x.rstrip() for x in f.read_text(encoding='utf-8').splitlines())+'\n',encoding='utf-8')


if __name__=='__main__':main()
