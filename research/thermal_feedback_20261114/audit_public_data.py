"""Read fixed-author artifacts. No fitting or transfer to the synthetic two-resource model."""
import csv,json,hashlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent;CACHE=ROOT.parent/'throttle_sources/sev/05_results';OUT=ROOT/'results';OUT.mkdir(exist_ok=True)
def rows(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
records=[];bins=[]
for path in sorted((CACHE/'runs').glob('*/telemetry_raw.csv')):
    rr=rows(path);ii=rows(path.parent/'inference_log.csv');state=path.parent.name.split('_')[-1]
    col=lambda key:np.array([float(r[key]) for r in rr]);t=col('monotonic_offset_s');T=col('temp_soc_c');f=col('cpu_freq_mhz');flag=col('throttled_now').astype(int);uv=col('undervolt_now').astype(int)
    it=np.array([float(r['monotonic_time_s']) for r in ii]);lat=np.array([float(r['latency_ms']) for r in ii]);frame=np.array([int(r['frame_index']) for r in ii]);valid=it>=10
    first=int(np.flatnonzero(flag)[0]) if flag.any() else None
    high=T>=80;steady=t>=1500
    records.append({'state':state,'run':path.parent.name,'telemetry_rows':len(rr),'inference_rows':len(ii),'span_s':float(t[-1]-t[0]),'median_telemetry_step_s':float(np.median(np.diff(t))),'temperature_min_C':float(T.min()),'temperature_max_C':float(T.max()),'last300s_mean_C':float(T[steady].mean()),'frequency_values_MHz':sorted(set(f)),'active_throttle_flag_samples':int(flag.sum()),'observed_0to1_flag_transitions':int(np.sum(np.diff(flag,prepend=0)==1)),'undervoltage_flag_samples':int(uv.sum()),'first_flag_time_s':float(t[first]) if first is not None else None,'first_flag_temp_C':float(T[first]) if first is not None else None,'first_flag_freq_MHz':float(f[first]) if first is not None else None,'post10s_fps_author_formula':float(valid.sum()/(it[valid][-1]-it[valid][0])),'mean_inference_latency_ms':float(lat[valid].mean()),'frame_indices_contiguous':bool(np.array_equal(frame,np.arange(len(frame)))),'first10000_frames_completed_at_s':float(it[9999]),'high_temp_frequency_min_MHz':float(f[high].min()) if high.any() else None,'precision_labels':sorted({r['model_precision'] for r in ii})})
    # Nearest preceding telemetry sample; descriptive alignment, not an exact
    # within-frame frequency measurement or causal latency coefficient.
    ix=np.searchsorted(t,it,side='right')-1;ix=np.clip(ix,0,len(t)-1)
    for freq in sorted(set(f)):
        mask=valid&(f[ix]==freq)
        if mask.sum()<5:continue
        bins.append({'state':state,'preceding_telemetry_freq_MHz':freq,'frames':int(mask.sum()),'median_latency_ms':float(np.median(lat[mask])),'p10_latency_ms':float(np.quantile(lat[mask],.1)),'p90_latency_ms':float(np.quantile(lat[mask],.9)),'interpretation':'Descriptive bins only: frequency can change inside frame; clocks/sampling and thermal/load confounding remain.'})
summary=rows(CACHE/'condition_stats_paper.csv');lookup={r['condition']:r for r in summary}
data={'source_commit':'faddf01ffb3d1651f2b654faa77eaee59fbbde4a','scope':'One preselected replicate per static state; no new device experiments or original-author scripts executed','selected_static_runs':records,'author_reported_conditions':summary,'proactive_gain_vs_static_S1_energy_per_frame_pct':100*(float(lookup['Static-S1']['j_per_frame'])-float(lookup['Proactive']['j_per_frame']))/float(lookup['Static-S1']['j_per_frame']),'raw_external_power_available':False,'raw_power_note':'Repository README: raw PowerZ databases available on request; included CSV is aggregate/derived, not a synchronized full-window power trace. No request sent.','critical_boundaries':['Active throttle flag samples are not independently counted hardware events.','Official Raspberry Pi guidance describes progressive throttling from 80C and further at85C; paper85C should not be copied as a universal first-trip threshold.','No exact frequency transition latency, hardware release hysteresis or two-resource RC can be identified from these files.','No Pi coefficients are transferred into a heterogeneous AGX/NPU model.']}
(OUT/'public_data_audit.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for name,rr in [('public_static_runs.csv',records),('public_latency_frequency_bins.csv',bins)]:
    with (OUT/name).open('w',newline='',encoding='utf-8') as file:
        w=csv.DictWriter(file,fieldnames=list(rr[0]));w.writeheader();w.writerows(rr)
print(json.dumps({'runs':records,'proactive_vs_static_S1_pct':data['proactive_gain_vs_static_S1_energy_per_frame_pct']},ensure_ascii=False))
