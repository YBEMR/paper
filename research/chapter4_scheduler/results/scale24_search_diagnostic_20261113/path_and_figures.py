"""Compare saved paths and render scientific figures; no scientific reruns."""
from pathlib import Path
from fractions import Fraction as F
from copy import deepcopy
import csv
import hashlib
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT=Path(__file__).resolve().parent
REPO=next(p for p in OUT.parents if (p/'RESEARCH_BRIEF.md').is_file())
EX=REPO/'research/chapter4_scheduler/results/scale24_i1_20261113/execution'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
digest=lambda v:hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
save=lambda n,v:(OUT/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
d=read(OUT/'diagnostic.json')
ids={'ON':'03_U03__n24_ON_I1','OFF':'02_U03__n24_OFF_I1'}
raw={a:read(EX/'calls'/sid/'method/result.json') for a,sid in ids.items()}
maps={}
for arm,r in raw.items():
    current=r['initial_safe_snapshot']['candidate'];maps[arm]={}
    steps=iter(d['runs'][ids[arm]]['steps'])
    for p in r['graph_proposals']:
        if not p['strict_accepted']:continue
        step=next(steps);t=p['energy_target'];key=(t['scene_id'],t['stage_id'],t['target_opp'])
        maps[arm][key]={'packet':p,'before':current,'step':step};current=p['candidate']

matched=[]
for key,on in maps['ON'].items():
    if key not in maps['OFF']:continue
    off=maps['OFF'][key];sid=key[0];op,fp=on['packet'],off['packet']
    matched.append({'target':key,'ON_step':on['step']['step'],'OFF_step':off['step']['step'],
        'ON_time_s':on['step']['formed_at_s'],'OFF_time_s':off['step']['formed_at_s'],
        'ON_energy_J':float(F(on['step']['energy_upper_J'])),'OFF_energy_J':float(F(off['step']['energy_upper_J'])),
        'same_base_scene':on['before']['scenes'][sid]==off['before']['scenes'][sid],
        'same_after_scene':op['candidate']['scenes'][sid]==fp['candidate']['scenes'][sid],
        'same_selected_stages':op['selected_stages']==fp['selected_stages'],
        'ON_extra_edges':op['additional_reversed_edges'],'OFF_extra_edges':fp['additional_reversed_edges']})

key=('C2','C2::S2.s0008.r1','L');on,off=maps['ON'][key],maps['OFF'][key]
op,fp=on['packet'],off['packet']
assert on['before']['scenes']['C2']==off['before']['scenes']['C2']
assert op['selected_stages']==fp['selected_stages']
assert op['nonthermal_by_scene']['C2']==fp['nonthermal_by_scene']['C2']
opps=lambda p:{x['stage_id']:x['opp'] for x in p['candidate']['scenes']['C2'] if x['stage_id'] in p['selected_stages']}
assert opps(op)==opps(fp)
hashes={};availability={}
for context,own,priorraw in (('ON',op,raw['ON']),('OFF',fp,raw['OFF'])):
    context_hashes={}
    for layout,p in (('reverse_ON',op),('incumbent_OFF',fp)):
        identity_envelope=deepcopy(own['candidate'])
        identity_envelope['scenes']['C2']=p['candidate']['scenes']['C2']
        context_hashes[layout]=digest(identity_envelope)
    hashes[context]=context_hashes
    step=on['step'] if context=='ON' else off['step'];round_id=step['step']-1
    gs=[x for x in csv.DictReader((OUT/'graph_groups.csv').open(encoding='utf-8-sig')) if x['slot']==ids[context] and int(x['round'])==round_id]
    diags=[priorraw['reconstruction_attempts'][int(g['diag_index'])] for g in gs]
    available=[]
    for orientation in ('incumbent','reverse'):
        ok=[x for x in diags if x['target']['stage_id']==key[1] and x['target']['target_opp']==key[2]
            and x['selected_stages']==own['selected_stages'] and x['opp_overrides']==opps(own)
            and x['orientation']==orientation and x['template']=='earliest' and x['state']=='COMPLETE_LEGAL_CANDIDATE']
        assert ok;available.append(orientation)
    old_seen={x['candidate_sha256'] for x in priorraw['evaluations'] if x['returned_at_s']<own['proposed_at_s']}
    assert not any(h in old_seen for h in context_hashes.values())
    availability[context]={'both_orientations_archived_as_legal':available,'neither_identity_evaluated_before_proposal':True}
assert hashes['ON']['reverse_ON']==op['candidate_sha256']
assert hashes['OFF']['incumbent_OFF']==fp['candidate_sha256']
assert hashes['ON']['reverse_ON']<hashes['ON']['incumbent_OFF']
assert hashes['OFF']['incumbent_OFF']<hashes['OFF']['reverse_ON']
tie={'target':key,'same_C2_incumbent':True,'same_selected_modes':True,
    'same_C2_nonthermal_ledger':True,'C2_nonthermal_energy_J':op['nonthermal_by_scene']['C2']['nonthermal_energy_J'],
    'ON_selected_orientation':op['orientation'],'OFF_selected_orientation':fp['orientation'],
    'hash_comparisons':hashes,'availability':availability,
    'scope':'Only identity envelopes of saved scenes were combined for hash comparison; no candidate scheduled or evaluated.'}

milestone=('C2','C2::L1.s0003.r1','L')
mo,mf=maps['ON'][milestone]['step'],maps['OFF'][milestone]['step']
laston=d['runs'][ids['ON']]['steps'][-1];lastoff=d['runs'][ids['OFF']]['steps'][-1]
tail={'common_target':milestone,'ON_milestone_s':mo['formed_at_s'],'OFF_milestone_s':mf['formed_at_s'],
    'ON_milestone_J':mo['energy_upper_J'],'OFF_milestone_J':mf['energy_upper_J'],
    'ON_remaining_drop_J':str(F(mo['energy_upper_J'])-F(laston['energy_upper_J'])),
    'OFF_remaining_drop_J':str(F(mf['energy_upper_J'])-F(lastoff['energy_upper_J'])),
    'final_ON_minus_OFF_J':str(F(laston['energy_upper_J'])-F(lastoff['energy_upper_J'])),
    'ON_tail_targets':[x['target'] for x in d['runs'][ids['ON']]['steps'] if x['step']>mo['step']],
    'OFF_tail_targets':[x['target'] for x in d['runs'][ids['OFF']]['steps'] if x['step']>mf['step']],
    'scope':'Arithmetic of observed milestones; not a counterfactual or isolated causal decomposition.'}
late_target_evidence={}
groups=list(csv.DictReader((OUT/'graph_groups.csv').open(encoding='utf-8-sig')))
for arm,entry in (('ON',maps['ON'][milestone]),('OFF',maps['OFF'][milestone])):
    rr=entry['step']['step']-1;items=[]
    for g in groups:
        if g['slot']==ids[arm] and int(g['round'])==rr and g['target']==milestone[1] and g['target_opp']=='L':
            items.append({'diag_index':int(g['diag_index']),'base_reason':g['base_reason'],'extra_count':int(g['extra_count'])})
            diag=raw[arm]['reconstruction_attempts'][int(g['diag_index'])]
            chosen_opps={x['stage_id']:x['opp'] for x in entry['packet']['candidate']['scenes']['C2'] if x['stage_id'] in entry['packet']['selected_stages']}
            items[-1].update(opps=diag['opp_overrides'],orientation=diag['orientation'],template=diag['template'],
                same_as_selected_modes=diag['opp_overrides']==chosen_opps,deadline_violations=diag['deadline_violations'])
    late_target_evidence[arm]=items
save('path_comparison.json',{'matched_targets':matched,'global_hash_tie_break':tie,'tail_bookkeeping':tail,'C2_L1s0003_current_round_base_records':late_target_evidence})

plt.rcParams.update({'font.family':'DejaVu Sans','svg.fonttype':'none','font.size':10})
colors={'ON':'#b5473b','OFF':'#176b9a'}
fig,axes=plt.subplots(1,2,figsize=(11,4.4),layout='constrained')
for ax in axes:
    for arm,sid in ids.items():
        points=d['runs'][sid]['curve'];xs=[x['time_s'] for x in points]+[300];ys=[x['energy_upper_J_decimal'] for x in points]+[points[-1]['energy_upper_J_decimal']]
        ax.step(xs,ys,where='post',color=colors[arm],label=arm+'-I1',linewidth=1.7)
    ax.set_xlabel('Method elapsed time (s)');ax.set_ylabel('SAFE energy upper bound (J)');ax.grid(alpha=.2)
    ax.axvline(180,color='#777777',linestyle=':',linewidth=1);ax.legend(loc='upper right')
axes[0].set_xlim(0,300);axes[0].set_title('U03 / 24 Stage: full 300 s budget')
axes[1].set_xlim(180,300);axes[1].set_ylim(3.38,5.08);axes[1].set_title('Search window: accepted SAFE receipts')
for count,step in enumerate([x for x in d['runs'][ids['ON']]['steps'] if x['extra_edges']],1):
    x=step['formed_at_s'];y=float(F(step['energy_upper_J']));axes[1].scatter([x],[y],marker='D',s=34,color=colors['ON'],zorder=5)
    axes[1].annotate(f'Extra edge {count}\n{x:.3f} s',(x,y),xytext=(7,12),textcoords='offset points',fontsize=9)
fig.savefig(OUT/'U03_energy_time.png',dpi=180);fig.savefig(OUT/'U03_energy_time.svg');plt.close(fig)

prefix=list(csv.DictReader((OUT/'U04_initialization_prefix.csv').open(encoding='utf-8-sig')))
fig,axes=plt.subplots(1,2,figsize=(11,4.1),layout='constrained')
for arm in ('ON','OFF'):
    pts=[x for x in prefix if x.get(arm+'_returned_s')]
    axes[0].plot([int(x['ordinal']) for x in pts],[float(x[arm+'_returned_s']) for x in pts],label=arm+'-I1',color=colors[arm])
    tailpts=pts[43:]
    axes[1].plot([int(x['ordinal']) for x in tailpts],[float(x[arm+'_admitted_s']) for x in tailpts],marker='o',label=arm+' admission',color=colors[arm])
for ax in axes:
    ax.axhline(180,color='#777777',linestyle=':',label='180 s admission gate');ax.grid(alpha=.2);ax.legend()
    ax.set_xlabel('Initialization evaluation ordinal');ax.set_ylabel('Method elapsed time (s)')
axes[0].set_title('U04: identical candidate / energy prefix (49)');axes[1].set_title('Faster common prefix admits evaluations 50–51')
fig.savefig(OUT/'U04_initialization_gate.png',dpi=180);fig.savefig(OUT/'U04_initialization_gate.svg');plt.close(fig)
for name in ('U03_energy_time.svg','U04_initialization_gate.svg'):
    svg=OUT/name
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text(encoding='utf-8').splitlines())+'\n',encoding='utf-8')
print(json.dumps({'tie_break_verified':True,'hashes':hashes,'tail':{k:v for k,v in tail.items() if not k.endswith('targets')}},ensure_ascii=False,indent=2))
