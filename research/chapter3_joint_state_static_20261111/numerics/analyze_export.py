"""Static array/metadata audit only. No model import or scientific solver."""
from collections import defaultdict, Counter
from datetime import datetime, timezone
import csv
import json
from pathlib import Path
import time
import numpy as np

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
ORIGIN=REPO/'research/chapter3_support_autol_lp_20261111/autol_build/rev02/execution/on'
started=datetime.now(timezone.utc).isoformat();begin=time.monotonic()
z=np.load(ORIGIN/'exported_model.npz',allow_pickle=False)
matrix_data=z['A_data'];row_ptr=z['A_indptr'];upper=z['ub'];lower=z['lb']
names=json.loads((ORIGIN/'variable_names.json').read_text());families=defaultdict(list)
for line in (HERE/'row_metadata.jsonl').open():
 r=json.loads(line);i=r['row_index'];families[r['tag'].split('/')[0]].append(i)
rows=[];hist={}
for family,indices in families.items():
 data=np.concatenate([matrix_data[row_ptr[i]:row_ptr[i+1]] for i in indices]);a=np.abs(data[data!=0])
 rows.append(dict(family=family,rows=len(indices),nnz=len(data),min_abs=float(a.min()) if a.size else None,
     max_abs=float(a.max()) if a.size else None,below_1e_9=int(np.sum(a<1e-9)),
     abs_q10=float(np.quantile(a,.1)) if a.size else None,
     abs_median=float(np.median(a)) if a.size else None,
     abs_q90=float(np.quantile(a,.9)) if a.size else None))
 hist[family]={str(k):int(v) for k,v in Counter(np.floor(np.log10(a)).astype(int)).items()}
with (HERE/'coefficient_by_family.csv').open('x',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
(HERE/'coefficient_log10_histogram.json').write_text(json.dumps(hist,indent=2))
# Reproduce the preceding arithmetic estimate from archived names/bounds.
counts=Counter();k={};S=Counter()
for i,n in enumerate(names):
 if n.startswith('q:'):
  _,sid,l,node=n.split(':');k.setdefault((sid,int(l)),4);k[sid,int(l)]+=int(upper[i]>lower[i])
 if n.startswith('w:'):
  _,sid,l,state=n.split(':',3);S[sid,int(l)]+=1
assert set(k)==set(S)
computed=dict(current_physical_rows=sum(10*s for s in S.values()),
    disaggregated_source_bound_rows=sum(2*k[key]*s for key,s in S.items()),
    source_link_rows=sum(2*v for v in k.values()),output_rows=10*len(k),
    extra_copies=sum(k[key]*s for key,s in S.items()))
computed['disaggregated_physical_rows']=sum(computed[n] for n in ['disaggregated_source_bound_rows','source_link_rows','output_rows'])
existing=json.loads((HERE/'compact_expression_estimate.json').read_text());assert computed==existing['totals']
assert len(families)==18 and sum(r['rows'] for r in rows)==124338 and sum(r['nnz'] for r in rows)==1311146
record=dict(started_utc=started,ended_utc=datetime.now(timezone.utc).isoformat(),wall_s=time.monotonic()-begin,
    coefficient_families=len(families),all_rows_partitioned=True,all_nonzeros_partitioned=True,
    compact_estimate_replayed=True,new_model_build_calls=0,new_solver_calls=0,new_thermal_calls=0)
(HERE/'export_analysis_receipt.json').write_text(json.dumps(record,indent=2));print(json.dumps(record,indent=2))
