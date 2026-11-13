"""Artificial tests and archived-state structural checks; no thermal reruns."""
import argparse
from collections import Counter
from copy import deepcopy
from itertools import islice
import io
import json
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from ..scaling import run as shared
from .prefilter import RoundFilter, new_counts
from .packets import candidate_packets, ORIGINAL_PACKETS
from ..tests.test_method import FakeClock
from timing import MethodBudget

REPO=shared.REPO
OLD=REPO/'research/chapter4_scheduler/results/scale24_i1_20261113'
DIAG=OLD.parent/'scale24_search_diagnostic_20261113'


def run(out):
    out.mkdir(parents=True,exist_ok=False)
    began=time.monotonic();result={'passed':False,'failures':[],'errors':[],
        'real_method_calls':0,'thermal_evaluations':0,
        'scope':'Artificial full sequence/oracle checks and archived fixed-state structural regression; not generalization.'}
    try:
        # Existing I1 regression deliberately runs the I0 constructor on an
        # invented fixture with a MOCK_ONLY assessor. Keep that test intact;
        # forbid physical evaluation throughout the suite and archive checks.
        with patch('thermal.evaluate_candidate',side_effect=AssertionError('NO_REAL_THERMAL')):
            modules=['research.chapter4_scheduler.onp.test_onp',
                'research.chapter4_scheduler.onp.test_run',
                'research.chapter4_scheduler.blocking.tests.test_core',
                'research.chapter4_scheduler.blocking.tests.test_blocking_method',
                'research.chapter4_scheduler.blocking.tests.test_ablation',
                'research.chapter4_scheduler.i1.test_i1']
            suite=unittest.defaultTestLoader.loadTestsFromNames(modules)
            log=io.StringIO();t=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
            (out/'tests.log').write_text(log.getvalue(),encoding='utf-8')
            result.update(tests_run=t.testsRun,failures=[str(x) for x in t.failures],errors=[str(x) for x in t.errors])
            if not t.wasSuccessful():raise AssertionError('UNIT_OR_LIFECYCLE_CHECKS_FAILED')
            manifest=shared.read(OLD/'files_sha256.json');plan=shared.read(OLD/'execution/plan.json')
            for n,h in manifest.items():assert shared.sha(REPO/n)==h,n
            for n,h in plan['source_sha256'].items():assert shared.sha(REPO/n)==h,n
            result.update(old_archive_files_unchanged=len(manifest),frozen_source_files_unchanged=len(plan['source_sha256']))
            import csv
            groups=list(csv.DictReader((DIAG/'graph_groups.csv').open(encoding='utf-8-sig')))
            result['archived_necessary_conditions']=[];prefixes=[]
            for slot in [s for s in plan['slots'] if s['arm'] in ('ON','OFF')]:
                sid=slot['id'];folder=OLD/'execution/calls'/sid/'method'
                raw=shared.read(folder/'result.json');ins=shared.read(folder/'input_instance.json')
                states=[raw['initial_safe_snapshot']['candidate']]+[p['candidate'] for p in raw['graph_proposals'] if p['strict_accepted']]
                stats=Counter();guards={};records=raw['reconstruction_attempts'];gg=[g for g in groups if g['slot']==sid]
                for k,g in enumerate(gg):
                    rr=int(g['round']);idx=int(g['diag_index']);base=records[idx]
                    if rr not in guards:guards[rr]=RoundFilter(ins,states[rr],MethodBudget(300,clock=FakeClock()),new_counts())
                    guard=guards[rr]
                    bounds,cert=guard.group(base['scene_id'],base['selected_stages'],base['opp_overrides'],base['orientation'],base['template'])
                    end=int(gg[k+1]['diag_index']) if k+1<len(gg) else len(records)
                    extras=records[idx+1:end];stats['base_checked']+=1
                    if cert:
                        assert all(d['state']!='COMPLETE_LEGAL_CANDIDATE' for d in [base]+extras)
                        stats['base_pruned']+=1;stats['extras_covered_by_group_rejection']+=len(extras)
                    else:
                        stats['legal_bases_retained']+=base['state']=='COMPLETE_LEGAL_CANDIDATE'
                        for extra in extras:
                            ec=guard.edge(bounds,base,extra['extra_resource_edge'])
                            if ec:
                                assert extra['state']!='COMPLETE_LEGAL_CANDIDATE';stats['extra_pruned_individually']+=1
                            stats['legal_extras_retained']+=extra['state']=='COMPLETE_LEGAL_CANDIDATE'
                    stats['extra_checked_or_covered']+=len(extras)
                result['archived_necessary_conditions'].append({'slot':sid,**dict(stats)})
                print({'archive_guards_passed':sid,**dict(stats)},flush=True)
                # Eight emitted candidates, from initial and both extra-edge aftermaths.
                # Exhaustive full sequences are checked separately on artificial inputs.
                if slot['arm']=='ON':
                    state_ids=[0,1,11] if slot['root_id']=='U03' else [0]
                    for rr in state_ids:
                        for enabled in (False,True):
                            args=(ins,states[rr]);before=shared.digest(args)
                            old=list(islice(ORIGINAL_PACKETS(*args,MethodBudget(300,clock=FakeClock()),allow_blocking_edges=enabled),8))
                            new=list(islice(candidate_packets(*args,MethodBudget(300,clock=FakeClock()),allow_blocking_edges=enabled),8))
                            assert old==new and shared.digest(args)==before
                            prefixes.append({'slot':sid,'state_after_accepts':rr,'extra_enabled':enabled,
                                'identical_packet_prefix':len(old),'sha256':[shared.digest(p) for p in old]})
                    print({'ordered_prefix_checks_passed':sid},flush=True)
            result['ordered_archived_prefixes']=prefixes
            result['source_sha256']={**plan['source_sha256'],**{f.relative_to(REPO).as_posix():shared.sha(f) for f in Path(__file__).parent.glob('*.py')}}
            result['passed']=True
    except BaseException as error:
        result['errors'].append(repr(error));raise
    finally:
        result['wall_s']=time.monotonic()-began
        shared.save(out/'checks.json',result)
    print({'passed':True,'tests':result['tests_run'],'wall_s':result['wall_s']},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    run(p.parse_args().out.resolve())
