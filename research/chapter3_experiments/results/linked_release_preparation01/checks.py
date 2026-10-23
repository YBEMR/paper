"""K174 repeatable pure fixtures; no production imports or scientific calls."""
import argparse
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('k174_pure_draft', HERE/'prepare.py')
DRAFT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DRAFT)


def mode(stage, unit, domain, opp, duration, power):
    return {'shared_stage_id':stage, 'unit_id':unit, 'domain_id':domain,
            'opp_id':opp, 'duration_ms':str(duration), 'activity_power_W':str(power),
            'activity_energy_J':str(F(str(duration))*F(str(power))/1000)}


def fixture():
    instance = {'start_grid_ms':'1', 'window_ms':'20', 'stage_modes':{
        'O':[mode('O','N0','N','H',8,1)],
        'J':[mode('J','N0','N','H',2,2), mode('J','N0','N','L',4,'1/2')],
        'K':[mode('K','C0','C','L',1,1)]}}
    scene = {'id':'S', 'weight':'1/2',
        'stage_instances':[{'id':s, 'shared_stage_id':s, 'request_id':('R' if s!='O' else 'RO')}
                           for s in ('O','J','K')],
        'requests':[{'id':r,'release_ms':'0','deadline_ms':'20'} for r in ('R','RO')],
        'dependencies':[['J','K']]}
    warm = {'O':{'unit':'N0','opp':'H','start_ms':'0'},
            'J':{'unit':'N0','opp':'H','start_ms':'8'},
            'K':{'unit':'C0','opp':'L','start_ms':'10'}}
    return instance,scene,warm,['O']


def row(stage='x', unit='C1', domain='C', opp='L', start='0', end='1'):
    return dict(stage_id=stage,unit_id=unit,domain_id=domain,opp_id=opp,start_ms=start,end_ms=end)


class PureChecks(unittest.TestCase):
    def test_half_open_noninteger_and_domain(self):
        a=row(end='7/2'); b=row(stage='b',start='7/2',end='9/2')
        self.assertEqual(DRAFT.conflict(a,b,set()),[])
        b['start_ms']='17/5'
        self.assertEqual(DRAFT.conflict(a,b,set()),['same_unit'])
        b['unit_id']='C2'
        self.assertEqual(DRAFT.conflict(a,b,set()),[])
        b['opp_id']='H'
        self.assertEqual(DRAFT.conflict(a,b,set()),['same_domain_different_opp'])
        b['domain_id']='G'
        self.assertEqual(DRAFT.conflict(a,b,set()),[])

    def test_direct_edges_include_exact_boundary(self):
        a=row(stage='a',end='7/2'); b=row(stage='b',unit='G0',domain='G',start='7/2',end='8')
        self.assertEqual(DRAFT.conflict(a,b,{('a','b')}),[])
        b['start_ms']='17/5'
        self.assertEqual(DRAFT.conflict(a,b,{('a','b')}),['predecessor'])
        self.assertEqual(DRAFT.conflict(b,a,{('a','b')}),['successor'])
        self.assertEqual(DRAFT.conflict(a,b,{('other','b')}),[])

    def test_strong_trigger_and_all_retimings_blocked(self):
        i,s,w,o=fixture(); r=DRAFT.select_scene(i,s,w,o)
        self.assertEqual(r['selected'],'J'); self.assertEqual(r['opened'],['J','O'])
        t=r['triggers'][0]
        self.assertEqual(t['last_grid_start_ms'],'6')
        self.assertEqual([F(x['label']['start_ms']) for x in t['necessary_labels']],list(map(F,range(7))))
        self.assertTrue(all(x['open_anchor_resource_conflicts'] for x in t['necessary_labels']))

    def test_current_point_valid_no_trigger(self):
        i,s,w,o=fixture();w['K']['start_ms']='13'
        self.assertIsNone(DRAFT.select_scene(i,s,w,o)['selected'])

    def test_one_unblocked_necessary_start_prevents_trigger(self):
        i,s,w,o=fixture();i['stage_modes']['O']=[mode('O','N0','N','H',5,1)]
        r=DRAFT.select_scene(i,s,w,o)
        self.assertIsNone(r['selected'])
        self.assertTrue(any(v['necessary_label_count']>0 for v in r['rejected']))

    def test_no_grid_label_no_trigger(self):
        i,s,w,o=fixture();s['requests'][0]['release_ms']='8'
        r=DRAFT.select_scene(i,s,w,o)
        self.assertIsNone(r['selected']); self.assertEqual(r['rejected'][0]['necessary_label_count'],0)

    def test_already_lowest_activity_no_trigger(self):
        i,s,w,o=fixture();i['stage_modes']['O']=[mode('O','N0','N','H',6,1)]
        w['J'].update(opp='L',start_ms='6')
        self.assertIsNone(DRAFT.select_scene(i,s,w,o)['selected'])

    def test_non_slower_lower_energy_is_outside_this_rule(self):
        i,s,w,o=fixture();i['stage_modes']['J'][1]=mode('J','N0','N','L',1,'1/2')
        self.assertIsNone(DRAFT.select_scene(i,s,w,o)['selected'])

    def test_reordering_is_deterministic(self):
        i,s,w,o=fixture();expected=DRAFT.select_scene(i,s,w,o)
        j,t,v,p=deepcopy((i,s,w,o))
        j['stage_modes']={k:list(reversed(vals)) for k,vals in reversed(list(j['stage_modes'].items()))}
        t['stage_instances'].reverse();t['requests'].reverse();t['dependencies'].reverse()
        v=dict(reversed(list(v.items())))
        self.assertEqual(DRAFT.select_scene(j,t,v,p),expected)

    def test_at_most_one_released_and_one_stays_closed(self):
        i,s,w,o=fixture()
        # A second independent closed job has the same trigger and saving;
        # lexical tie selection must not release both.
        i['stage_modes']['J2']=[mode('J2','N0','N','H',2,2),mode('J2','N0','N','L',4,'1/2')]
        s['stage_instances'].append({'id':'J2','shared_stage_id':'J2','request_id':'R2'})
        s['requests'].append({'id':'R2','release_ms':'0','deadline_ms':'12'})
        w['J2']={'unit':'N0','opp':'H','start_ms':'10'}
        r=DRAFT.select_scene(i,s,w,o)
        self.assertEqual(len(r['triggers']),2)
        self.assertEqual(r['selected'],'J')
        self.assertLessEqual(len(set(r['opened'])-set(o)),1)
        self.assertTrue(set(r['opened'])<set(w))
        i,s,w,o=fixture();o=['O','K']
        self.assertEqual(DRAFT.select_scene(i,s,w,o)['reason'],'keep_one_closed_stage')

    def test_cyclic_or_invalid_identity_refused(self):
        for change in ('cycle','unknown_edge','duplicate_stage','missing_warm','invalid_mask','negative_duration','bad_ledger','off_grid','duplicate_mode'):
            i,s,w,o=fixture()
            if change=='cycle':s['dependencies'] += [['K','J']]
            elif change=='unknown_edge':s['dependencies'] += [['missing','J']]
            elif change=='duplicate_stage':s['stage_instances'].append(deepcopy(s['stage_instances'][0]))
            elif change=='missing_warm':w.pop('J')
            elif change=='invalid_mask':o=['O','O']
            elif change=='negative_duration':i['stage_modes']['J'][0]['duration_ms']='-2'
            elif change=='bad_ledger':i['stage_modes']['J'][0]['activity_energy_J']='100'
            elif change=='off_grid':w['J']['start_ms']='17/2'
            elif change=='duplicate_mode':i['stage_modes']['J'].append(deepcopy(i['stage_modes']['J'][0]))
            with self.subTest(change=change):
                with self.assertRaises((ValueError,KeyError)):
                    DRAFT.select_scene(i,s,w,o)

    def test_mask_union_preserves_old_membership_and_warm(self):
        i,s,w,o=fixture();r=DRAFT.select_scene(i,s,w,o)
        def member(stage,opp,start,mask):
            return stage in mask or (opp==w[stage]['opp'] and F(start)==F(w[stage]['start_ms']))
        for k in w:
            self.assertTrue(member(k,w[k]['opp'],w[k]['start_ms'],o))
            self.assertTrue(member(k,w[k]['opp'],w[k]['start_ms'],r['opened']))
            for m in i['stage_modes'][k]:
                for start in range(21):
                    if member(k,m['opp_id'],start,o):
                        self.assertTrue(member(k,m['opp_id'],start,r['opened']))
        # These are independent membership implications, not complete schedules.

    def test_existing_r1_r3_records_and_read_only_identity(self):
        p=HERE/'static_run01/facts.json';raw=p.read_bytes();facts=json.loads(raw)
        self.assertTrue(facts['source_unchanged']);self.assertEqual(facts['research_calls'],0)
        expected={('base__R1','AB_offset_0ms'):None,('base__R1','AC_offset_0ms'):None,
                  ('base__R3','AB_offset_0ms'):'AB_offset_0ms::B_r1::B.main',('base__R3','AC_offset_0ms'):None}
        self.assertEqual({(r['case_id'],r['scene_id']):r['selected'] for r in facts['records']},expected)
        for record in facts['records']:
            self.assertTrue(record['old_options_retained'])
            self.assertGreaterEqual(record['new_options'],record['old_options'])
        self.assertEqual(p.read_bytes(),raw)


def main(out):
    out=Path(out)
    if out.exists():raise FileExistsError('Append-only pure check run')
    out.mkdir(parents=True)
    start=time.perf_counter()
    sources={str(p.name):hashlib.sha256(p.read_bytes()).hexdigest() for p in (HERE/'prepare.py',Path(__file__))}
    sys.addaudithook(DRAFT.audit);sys.setprofile(DRAFT.profile)
    try:
        with (out/'unittest.txt').open('w',encoding='utf8') as stream:
            result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PureChecks))
    finally:sys.setprofile(None)
    passed=result.wasSuccessful() and all(v==0 for v in DRAFT.GUARD.values())
    payload={'passed':passed,'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
             'guard':DRAFT.GUARD,'source_sha256':sources,'research_calls':0,'models':0,'thermal_calls':0,
             'full_candidate_evaluations':0,'new_U':False,'elapsed_s':time.perf_counter()-start,
             'scope':'pure synthetic necessary-label fixtures and read-only old records; no full schedule enumeration'}
    (out/'checks.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(payload,ensure_ascii=False))
    if not passed:raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    main(parser.parse_args().out)
