"""Export one archived arm without running the thermal model."""
from pathlib import Path
import argparse,csv
import numpy as np
from model import METRICS
root=Path(__file__).resolve().parent
ap=argparse.ArgumentParser();ap.add_argument('arm',help='e.g. w1_d149500_t78_c1l1s1 (omit h0/h1)');ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
poolname=args.arm.split('_t')[0]
with np.load(root/'results'/(poolname+'_pool.npz')) as z:pool=z['pool'];configs=z['configs']
with np.load(root/'results'/(args.arm+'_raw.npz')) as z:metrics=z['metrics']
with args.out.open('w',encoding='utf-8',newline='') as f:
    w=csv.writer(f);w.writerow(['candidate_id','config_id','mapping_id','s0_ms','s1_ms','s2_ms','s3_ms','shared_legal',*METRICS])
    for i,row in enumerate(pool):w.writerow([i,int(row[0]),int(row[1]),*(row[2:6]*.1),int(row[6]),*metrics[i]])
print(f'Exported {len(pool)} candidates; NaN metrics identify shared-domain-illegal candidates, if any.')
