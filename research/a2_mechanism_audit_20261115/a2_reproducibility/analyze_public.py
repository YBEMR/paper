"""Descriptive reanalysis only; no simulated A2 observations. Python standard library."""
from pathlib import Path
from statistics import median,mean
from collections import defaultdict,Counter
import json,hashlib,argparse,csv,re,subprocess

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def config(x): return tuple(x['dvfs_config'][k] for k in ['cpu_freq','gpu_freq','memory_freq'])
DEADLINES=dict(squeezenet=13,mobilenetv2=14,alexnet=15,googlenet=18,inception3=60,resnet=15,shufflenetv2=16)
def analyze(root,out):
    records=[];manifest=[];empty=0; metadata=defaultdict(Counter);rail_n=0;rail_residual=0.0
    for p in sorted((root/'data').rglob('*.json')):
        data=json.loads(p.read_text()); rel=p.relative_to(root).as_posix()
        manifest.append(dict(path=rel,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size,records=len(data)))
        for i,x in enumerate(data):
            power=x['power_readings']['p_all']; trim=power[4:-1]
            for j,v in enumerate(power):
                rail_n+=1
                rail_residual=max(rail_residual,abs(v-sum(x['power_readings'][k][j] for k in ['p_cpu','p_gpu','p_soc','p_ddr'])))
            if not trim: empty+=1;continue
            rt=median(x['runtime_ms'])
            for key in ['num_observations','batch_size','core_affinity','threads','control_scenario','timing_method']:
                metadata[key][str(x.get(key))]+=1
            records.append(dict(model=p.parent.parent.name,ambient=int(p.parent.name),cfg=config(x),runtime_ms=rt,
                power_W=mean(trim),energy_J=rt*mean(trim)/1000,energy_all_J=rt*mean(power)/1000,
                temp_before=x['temperature']['before'],temp_after=x['temperature']['after'],n_runtime=len(x['runtime_ms']),
                n_power=len(power),n_power_trim=len(trim),path=rel,index=i))
    groups=defaultdict(list)
    for r in records:groups[(r['model'],r['ambient'],r['cfg'])].append(r)
    agg={k:{a:median(r[a] for r in v) for a in ['runtime_ms','power_W','energy_J','energy_all_J']} for k,v in groups.items()}
    inventory=[];results=[];details=[]
    for model in sorted(DEADLINES):
        for temp in [25,70]:
            rows=[r for r in records if r['model']==model and r['ambient']==temp]
            cfgs=Counter(r['cfg'] for r in rows)
            inventory.append(dict(model=model,ambient_C=temp,records=len(rows),unique_configurations=len(cfgs),
                repeat_count_distribution=dict(Counter(cfgs.values())),
                runtime_samples_range=[min(r['n_runtime'] for r in rows),max(r['n_runtime'] for r in rows)],
                power_samples_range=[min(r['n_power'] for r in rows),max(r['n_power'] for r in rows)],
                trimmed_power_samples_range=[min(r['n_power_trim'] for r in rows),max(r['n_power_trim'] for r in rows)],
                before_CPU_range_C=[min(r['temp_before']['cpu'] for r in rows),max(r['temp_before']['cpu'] for r in rows)],
                before_GPU_range_C=[min(r['temp_before']['gpu'] for r in rows),max(r['temp_before']['gpu'] for r in rows)]))
        common=sorted({k[2] for k in agg if k[:2]==(model,25)} & {k[2] for k in agg if k[:2]==(model,70)})
        def a(t,c):return agg[(model,t,c)]
        ratios={field:median(a(70,c)[field]/a(25,c)[field]-1 for c in common)*100 for field in ['runtime_ms','power_W','energy_J']}
        for metric in ['energy_J','energy_all_J']:
            for deadline in [None,DEADLINES[model]]:
                feasible={t:[c for c in common if deadline is None or a(t,c)['runtime_ms']<=deadline] for t in [25,70]}
                fixed=sorted(set(feasible[25])&set(feasible[70]))
                if not fixed:
                    results.append(dict(model=model,metric=metric,deadline_ms=deadline,status='NO_COMMON_FEASIBLE'));continue
                opt={t:min(feasible[t],key=lambda c:(a(t,c)[metric],c)) for t in [25,70]}
                fix=min(fixed,key=lambda c:((a(25,c)[metric]+a(70,c)[metric])/2,c))
                oracle=mean(a(t,opt[t])[metric] for t in [25,70]);fixedE=mean(a(t,fix)[metric] for t in [25,70])
                c0,c1=opt[25],opt[70]
                gap25=a(25,c1)[metric]-a(25,c0)[metric]; gap70=a(70,c0)[metric]-a(70,c1)[metric]
                both_legal=all(c in fixed for c in [c0,c1])
                results.append(dict(model=model,metric=metric,deadline_ms=deadline,status='OK',matched=len(common),
                    feasible25=len(feasible[25]),feasible70=len(feasible[70]),fixed_feasible=len(fixed),
                    opt25=c0,opt70=c1,fixed=fix,oracle_mean_J=oracle,fixed_mean_J=fixedE,
                    adaptation_upper_bound_pct=100*(fixedE-oracle)/fixedE,
                    ranking_reversal=bool(c0!=c1 and gap25>0 and gap70>0 and both_legal),
                    crossover_gaps_J=[gap25,gap70],both_optima_feasible_both_states=both_legal,
                    energy_table={str(t):{'opt25':a(t,c0)[metric],'opt70':a(t,c1)[metric],'fixed':a(t,fix)[metric]} for t in [25,70]},
                    runtime_table={str(t):{'opt25':a(t,c0)['runtime_ms'],'opt70':a(t,c1)['runtime_ms'],'fixed':a(t,fix)['runtime_ms']} for t in [25,70]}))
        details.append(dict(model=model,matched=len(common),median_paired_change_pct=ratios))
    result=dict(evidence='Observed profile reanalysis; in-sample frequency adaptation only; A2_NOT_IDENTIFIABLE',
                files=len(manifest),raw_records=len(records),empty_trim_exclusions=empty,
                rail_audit=dict(samples=rail_n,max_sum_residual_W=rail_residual,meaning='p_all numerically equals CPU+GPU+SOC+DDR; not verified whole-system input power'),
                metadata={k:dict(v) for k,v in metadata.items()},inventory=inventory,paired=details,comparisons=results)
    write(out/'edgeengine_results.json',result);write(out/'edgeengine_source_manifest.json',manifest)
    write(out/'edgeengine_aggregates.json',[dict(model=k[0],ambient_C=k[1],cfg=k[2],records=len(groups[k]),**v) for k,v in sorted(agg.items())])
    return result
def jll(root,out):
    rows=[]
    for p in sorted((root/'results/mech_dose').glob('*.tegra')):
        txt=p.read_text(); vals={}
        for key,pattern in dict(gpu_C=r'gpu@([\d.]+)C',tj_C=r'tj@([\d.]+)C',gpu_MHz=r'GR3D_FREQ \d+%@\[(\d+)\]',power_mW=r'VDD_IN (\d+)mW').items():
            v=list(map(float,re.findall(pattern,txt)))
            vals[key]=dict(n=len(v),mean=mean(v),min=min(v),max=max(v)) if v else None
        rows.append(dict(path=p.relative_to(root).as_posix(),**vals))
    p=root/'results/energy_cal/gov_mobilenet_g1020_r1.power.csv'
    trace=list(csv.DictReader(p.open()));t=[float(r['t']) for r in trace];power=[float(r['vdd_in_mw'])/1000 for r in trace]
    sampling=dict(path=p.relative_to(root).as_posix(),samples=len(t),duration_s=t[-1]-t[0],
        median_interval_ms=median(b-a for a,b in zip(t,t[1:]))*1000,mean_input_W=mean(power),
        trapezoid_J=sum((b-a)*(p+q)/2 for a,b,p,q in zip(t,t[1:],power,power[1:])))
    result=dict(evidence='sample-trace audit only; no controlled hot/cold or scheduling comparison',tegrastats=rows,power_example=sampling)
    write(out/'jll_sample_audit.json',result);return result
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--edge',type=Path,default=Path('work/EdgeEngine'));ap.add_argument('--jll',type=Path,default=Path('work/jll_samples'));ap.add_argument('--out',type=Path,default=Path('outputs/a2_results'));args=ap.parse_args()
    r=analyze(args.edge,args.out)
    print('EdgeEngine',r['files'],'files',r['raw_records'],'records; empty trim',r['empty_trim_exclusions'])
    for x in r['paired']:print(x)
    for x in r['comparisons']:
        if x['metric']=='energy_J' and x['deadline_ms'] is not None:print(x['model'],x['deadline_ms'],'oracle upper-bound %',round(x['adaptation_upper_bound_pct'],6),'reversal',x['ranking_reversal'])
    if args.jll.exists():print(json.dumps(jll(args.jll,args.out),indent=2))
