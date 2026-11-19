"""Count exact identical-input prefix opportunities from archived legality only."""
import csv
import json
from pathlib import Path
from collections import defaultdict
HERE=Path(__file__).resolve().parent
EXP=HERE.parents[1]
frozen=json.loads((EXP/'expanded_input.json').read_text(encoding='utf-8'))
counts=json.loads((HERE/'equivalence_counts.json').read_text(encoding='utf-8'))
rows=[]
for directory in sorted((EXP/'raw/expanded').glob('*25C')):
    result=json.loads((directory/'result.json').read_text(encoding='utf-8'))
    deps=json.loads((directory/'deployments.json').read_text(encoding='utf-8'))
    with (directory/'local.csv').open(encoding='utf-8',newline='') as f:
        local=list(csv.DictReader(f))
    allowed={(d['deployment'],s):tuple(r['opp'] for r in local if
        r['deployment']==d['deployment'] and int(r['scene'])==s and r['deadline_ok']=='True')
        for d in deps for s in range(4)}
    scene_counts=sorted([r for r in counts if r['case']==directory.name],key=lambda x:x['index'])
    active=set()
    for depth,scene in enumerate(scene_counts,1):
        active.update(scene['active_apps'])
        groups=defaultdict(list)
        for dep in deps:
            d=dep['deployment']
            signature=json.dumps({str(a):frozen['deployments'][d]['stages'][str(a)]
                                  for a in sorted(active)},sort_keys=True)
            groups[signature].append(d)
        unique=0
        for group in groups.values():
            first=group[0]
            n=1
            for s in range(depth):
                for d in group:
                    assert allowed[d,s]==allowed[first,s]
                n*=len(allowed[first,s])
            unique+=n
        original=sum(d['deadline_legal_prefixes'][depth-1] for d in deps)
        rows.append(dict(case=directory.name,depth=depth,
            original_prefix_evaluations=original,identical_input_prefix_classes=unique,
            removable_duplicate_prefixes=original-unique))
    print(directory.name, rows[-4:])
(HERE/'prefix_reuse_counts.json').write_text(json.dumps(rows,indent=2)+'\n',encoding='utf-8')
print('PASS; static metadata only, zero scheduling/thermal calls')
