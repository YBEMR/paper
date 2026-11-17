"""Static audit of pinned original artifacts. Never imports author modules."""
import ast,csv,hashlib,json,re,zipfile
from pathlib import Path
R=Path(__file__).resolve().parent;C=R.parent/'shared_memory_sources';H=C/'hax';O=R/'results';O.mkdir(exist_ok=True)
def read(q):return json.loads(q.read_text(encoding='utf-8'))
def save(n,x):(O/n).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
sources=read(R/'source_manifest.json');checks=[]
for row in sources:
    if row['status']=='UNAVAILABLE':continue
    q=C/row['id'];assert q.exists(),row['id'];data=q.read_bytes();ok=hashlib.sha256(data).hexdigest()==row['sha256'];assert ok,row['id'];checks.append(row['id'])
layer=read(H/'output_expected/layer_results.json');dla=read(H/'output_expected/dla_compute_times.json');emc=read(H/'output_expected/emc_results.json');trans=read(H/'output_expected/transition_results.json')
emc_values=[int(v.rstrip('%')) for row in emc.values() for v in row.values()]
neg=[{'entry':k,'layer_diff_ms':v['layer_diff'],'reported_total_ms':v['total_time']} for k,v in dla.items() if v['layer_diff']<0]
asttree=ast.parse((H/'src/z3_solver_multi_dnn.py').read_text());arrays={}
for node in asttree.body:
    if isinstance(node,ast.Assign) and isinstance(node.value,ast.List):
        for target in node.targets:
            if isinstance(target,ast.Name):
                try:arrays[target.id]=ast.literal_eval(node.value)
                except (ValueError,TypeError):pass
with zipfile.ZipFile(C/'HaX-CoNN_zenodo.zip') as z:
    names=[n for n in z.namelist() if not n.endswith('/') and '/.git/' not in n];data_paths=[n for n in names if n.endswith(('.csv','.json','.log','.profile'))];archive_emc=json.loads(z.read('HaX-CoNN/output/emc_results.json'))
    archive_ref=z.read('HaX-CoNN/.git/refs/heads/ismet-dagli').decode().strip()
rows=[]
for key,v in layer.items():rows.append({'artifact':'layer_results.json','key':key,'field':'total_gpu_time_ms','value':v['gpu']['total_gpu_time_ms'],'unit':'ms','status':'AUTHOR_PRECOLLECTED_SUMMARY_UNMATCHED_OPP_METADATA'})
for key,v in dla.items():rows.append({'artifact':'dla_compute_times.json','key':key,'field':'layer_diff','value':v['layer_diff'],'unit':'ms','status':'NEGATIVE_DERIVED_DIFFERENCE_DO_NOT_USE_AS_TASK_TIME' if v['layer_diff']<0 else 'DERIVED_DIFFERENCE_NOT_VALIDATED_TASK_TIME'})
for kind,row in emc.items():
    for kernel,v in row.items():rows.append({'artifact':'emc_results.json','key':kind+'/'+kernel,'field':'max_percent','value':int(v.rstrip('%')),'unit':'percent_of_current_EMC_capacity','status':'FREQUENCY_AND_TIMESTAMPS_DISCARDED'})
for key,v in trans.items():rows.append({'artifact':'transition_results.json','key':key,'field':'transition_cost','value':v['transition_cost'],'unit':'ms','status':'AUTHOR_DERIVED_SUMMARY_UNMATCHED_OPP_METADATA'})
with (O/'hax_extracted_summaries.csv').open('w',newline='',encoding='utf-8-sig') as f:w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
result={'status':'STATIC_ARTIFACT_AUDIT_COMPLETE_NOT_A_SCHEDULING_EXPERIMENT','source_files_hash_checked':len(checks),'github_commit':read(R/'hax_selection.json')['commit'],'read_text_files':len(read(R/'hax_selection.json')['files']),'gpu_group_count':len(layer),'gpu_group_sum_ms_descriptive_only':sum(v['gpu']['total_gpu_time_ms'] for v in layer.values()),'dla_entries':len(dla),'negative_derived_differences':neg,'emc_peak_percent_count':len(emc_values),'emc_peak_percent_range':[min(emc_values),max(emc_values)],'transition_summary_entries':len(trans),'parsed_literal_array_lengths':{k:len(v) for k,v in arrays.items()},'raw_array_warning':'Recorded arrays exist, but have no joint task/precision/actual-clock/EMC/thermal/power provenance for this requested model; not fitted or executed.','zenodo':{'doi':'10.5281/zenodo.10225025','head_ref_in_zip':archive_ref,'non_git_regular_files':len(names),'tabular_or_profile_files':data_paths,'emc_entries':sum(len(x) for x in archive_emc.values()),'scope':'Current archive worktree plus member inventory; packed git history not exhaustively mined.'},'source_code_findings':{'emc_shell_preserves':'Percentage only; strips EMC MHz, timestamps, temperatures, power rails','emc_aggregation':'max(values), not mean trace or bytes/sec','orin_precision':'INT8; Xavier demonstration uses FP16','fallback':'GPU_FALLBACK enabled; README notes prob layer cannot run on DLA','version_conflict':'README opening says TRT 8.4.0/CUDA11.2, later Orin text TRT8.5/8.5.2; official JP5.1.1 says TRT8.5.2/CUDA11.4'},'joint_numeric_admissible':False,'no_repairs':['No clipping negative layer differences','No interpreting EMC percent as GB/s','No assigning all summary files Orin provenance','No executing Z3, TensorRT, tegrastats, shell or engines']}
save('artifact_audit.json',result)
print(json.dumps({k:result[k] for k in ['source_files_hash_checked','gpu_group_count','dla_entries','negative_derived_differences','emc_peak_percent_count','transition_summary_entries','zenodo','joint_numeric_admissible']},ensure_ascii=False))
