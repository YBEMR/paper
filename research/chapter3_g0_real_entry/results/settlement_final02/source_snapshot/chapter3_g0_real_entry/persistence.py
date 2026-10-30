"""Durable full-SAFE checkpoints; recovery does no physics or integration."""
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
import math

from .launch_contract import save,read,digest


def scope_evidence(budget,record_scope):
    """Resolve while the producing root is alive; never rewrite the record."""
    token=record_scope if isinstance(record_scope,str) else record_scope.get('token') if isinstance(record_scope,dict) else None
    if not isinstance(record_scope,(str,dict)):
        raise ValueError('SCOPE_REFERENCE_REQUIRED')
    snapshot=budget.scope_snapshot(token)
    if isinstance(record_scope,dict) and record_scope!=snapshot:
        raise ValueError('SCOPE_SNAPSHOT_DRIFT')
    parents=[];seen={snapshot['token']};parent=snapshot.get('parent_token')
    while parent is not None:
        if parent in seen:raise ValueError('CYCLIC_SCOPE')
        seen.add(parent)
        item=budget.scope_snapshot(parent);parents.append(item);parent=item.get('parent_token')
    return {'snapshot':snapshot,'parents':parents}


def validate_scope(evidence,record_scope,root,formed):
    if not isinstance(evidence,dict):raise ValueError('SCOPE_EVIDENCE_MISSING')
    snapshot=evidence.get('snapshot');parents=evidence.get('parents')
    if not isinstance(snapshot,dict) or not isinstance(parents,list):
        raise ValueError('SCOPE_EVIDENCE_MALFORMED')
    if (isinstance(record_scope,str) and snapshot.get('token')!=record_scope
            or isinstance(record_scope,dict) and snapshot!=record_scope
            or not isinstance(record_scope,(str,dict))):
        raise ValueError('SCOPE_REFERENCE_DRIFT')
    chain=[snapshot]+parents;seen=set()
    for index,item in enumerate(chain):
        if not isinstance(item,dict):raise ValueError('SCOPE_PARENT_MALFORMED')
        token=item.get('token');opened=item.get('opened_at_elapsed_s');end=item.get('deadline_elapsed_s')
        if (item.get('root_identity')!=root or type(opened) not in (int,float)
                or type(end) not in (int,float) or not all(math.isfinite(v) for v in (opened,end))
                or not 0<=opened<=formed<end<=300 or item.get('closed',False) is not False
                or token in seen):
            raise ValueError('LATE_CLOSED_OR_FOREIGN_SCOPE')
        seen.add(token)
        parent=chain[index+1] if index+1<len(chain) else None
        if parent is None:
            if item.get('parent_token') is not None:raise ValueError('MISSING_SCOPE_PARENT')
        elif (not isinstance(parent,dict) or item.get('parent_token')!=parent.get('token')
              or end>parent.get('deadline_elapsed_s',-1)
              or opened<parent.get('opened_at_elapsed_s',float('inf'))):
            raise ValueError('SCOPE_PARENT_DRIFT')
        if token is None and (index!=0 or parents or item.get('kind')!='root' or end!=300 or opened!=0):
            raise ValueError('INVALID_ROOT_SCOPE')


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
        evidence=scope_evidence(b,record.get('scope'))
        validate_scope(evidence,record.get('scope'),b.root_identity,record['completed_at_elapsed_s'])
        envelope={'schema':'g0-complete-safe-checkpoint-v2','plan_sha256':ctx['plan_sha256'],
            'input_sha256':ctx['plan']['input_sha256'],
            'source_manifest_sha256':digest(ctx['plan']['source_sha256']),
            'root_identity':deepcopy(b.root_identity),'record':deepcopy(record),
            'scope_evidence':evidence,
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
    selected=None;errors=[];incomplete=[];files_seen=0
    for path in sorted(Path(folder).glob('[0-9]*.json')):
        if '.seal.' in path.name:continue
        files_seen+=1
        if not path.with_suffix('.seal.json').is_file():
            incomplete.append({'path':str(path),'reason':'UNSEALED_PUBLICATION_NOT_A_CERTIFICATE'})
            continue
        try:
            e=read(path);seal=read(path.with_suffix('.seal.json'));r=e['record']
            if e.get('schema')!='g0-complete-safe-checkpoint-v2':
                raise ValueError('CHECKPOINT_SCOPE_EVIDENCE_VERSION_REQUIRED')
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
            validate_scope(e.get('scope_evidence'),r.get('scope'),root,times[0])
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
    return {'status':'ERROR' if errors else 'RECOVERED' if selected is not None else 'EMPTY',
            'files_seen':files_seen,'retained':selected is not None,'record':selected,'rejected':errors,
            'incomplete':incomplete,
            'scope':'existing full receipt only; no new integration or energy'}
