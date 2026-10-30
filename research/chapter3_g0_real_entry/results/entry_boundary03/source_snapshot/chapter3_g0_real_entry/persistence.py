"""Durable full-SAFE checkpoints; recovery does no physics or integration."""
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
import math

from .launch_contract import save,read,digest


class CheckpointStore:
    def __init__(self,folder,permit,budget,config,instance):
        self.folder=Path(folder);self.permit=permit;self.budget=budget
        self.config,self.instance=config,instance;self.index=0

    def __call__(self,record):
        b=self.budget
        # Never publish a newly accepted or serialized SAFE outside root time.
        if b.elapsed>=b.seconds:return
        self.index+=1
        p=self.folder/f'{self.index:06d}.json'
        ctx=self.permit.context
        envelope={'schema':'g0-complete-safe-checkpoint-v1','plan_sha256':ctx['plan_sha256'],
            'input_sha256':ctx['plan']['input_sha256'],
            'source_manifest_sha256':digest(ctx['plan']['source_sha256']),
            'root_identity':deepcopy(b.root_identity),'record':deepcopy(record),
            'written_at_elapsed_s':b.elapsed}
        save(p,envelope)
        if b.elapsed>=b.seconds:return
        save(p.with_suffix('.seal.json'),{'checkpoint_sha256':digest(envelope),
            'published_at_elapsed_s':b.elapsed})


def recover(folder,context,config,instance,method_start):
    """Read-only structural revalidation of existing complete receipts.

    This preserves a prior certificate, does not independently re-certify heat.
    Real post on a crashed/abnormal method is deliberately not auto-launched.
    """
    from ..chapter3_g0.receipts import Archive
    from ..chapter3_g0.contract import canonical_hash
    from .receipts import receipt_source_identity,_legacy
    validate_schedule=_legacy('schedules').validate_schedule
    selected=None;errors=[]
    for path in sorted(Path(folder).glob('[0-9]*.json')):
        if '.seal.' in path.name:continue
        try:
            e=read(path);seal=read(path.with_suffix('.seal.json'));r=e['record']
            if r.get('evidence_kind')!='REAL':raise ValueError('NON_REAL_CHECKPOINT')
            if (seal['checkpoint_sha256']!=digest(e) or e['plan_sha256']!=context['plan_sha256']
                    or e['input_sha256']!=context['plan']['input_sha256']
                    or e['source_manifest_sha256']!=digest(context['plan']['source_sha256'])):
                raise ValueError('CHECKPOINT_IDENTITY_OR_SEAL')
            times=[r['completed_at_elapsed_s'],e['written_at_elapsed_s'],seal['published_at_elapsed_s']]
            if (any(type(t) not in (int,float) or not math.isfinite(t) for t in times)
                    or not 0<=times[0]<=times[1]<=times[2]<300):
                raise ValueError('LATE_OR_INCOMPLETE_CHECKPOINT')
            root=e['root_identity']
            if float(root['start'])!=method_start or float(root['seconds'])!=300:
                raise ValueError('FOREIGN_ROOT')
            if r['generation_sha256']!=canonical_hash({k:v for k,v in r.items() if k!='generation_sha256'}):
                raise ValueError('GENERATION_DRIFT')
            if r['input_sha256']!=canonical_hash(instance) or r['config_sha256']!=canonical_hash(config):
                raise ValueError('INPUT_CONFIG_DRIFT')
            if validate_schedule(instance,r['candidate']).get('state')!='SCHEDULE_VALID_THERMAL_UNCHECKED':
                raise ValueError('INVALID_CHECKPOINT_SCHEDULE')
            budget=SimpleNamespace(seconds=300,root_identity=root)
            archive=Archive.__new__(Archive)
            archive._initialize(config,instance,budget,receipt_source_identity(),
                                accuracy=config['accuracy_targets'],evidence_kind='REAL')
            archive.validate_aggregate(r['candidate'],r['aggregate'])
            if (r['source_sha256']!=receipt_source_identity()
                    or Fraction(r['U_J'])!=Fraction(r['aggregate']['safe_upper_bound_J'])
                    or r['weighted_energy_J']!=r['aggregate']['weighted_energy_J']):
                raise ValueError('CHECKPOINT_ENERGY_OR_SOURCE_DRIFT')
            if selected is None or Fraction(r['U_J'])<Fraction(selected['U_J']):selected=r
        except Exception as error:
            errors.append({'path':str(path),'error':type(error).__name__+': '+str(error)})
    return {'retained':selected is not None,'record':selected,'rejected':errors,
            'scope':'existing full receipt only; no new integration or energy'}
