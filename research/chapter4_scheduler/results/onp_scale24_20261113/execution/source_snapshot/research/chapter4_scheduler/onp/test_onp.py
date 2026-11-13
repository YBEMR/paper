"""Bounded artificial correctness checks. No real HEFT/thermal calls."""
from contextlib import ExitStack
from copy import deepcopy
from fractions import Fraction as F
from itertools import product
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.chapter4_scheduler.tests.test_graph_core import fixture, rows, independent_legality
from research.chapter4_scheduler.tests.test_method import FakeClock, complete_mock, RESEARCH
from research.chapter4_scheduler.blocking.tests.test_core import artificial, crossing_fixture
from research.chapter4_scheduler.blocking.tests.test_blocking_method import crossing_input
from research.chapter4_scheduler.blocking import core, method as frozen
from .prefilter import RoundFilter, new_counts
from .packets import candidate_packets, ORIGINAL_PACKETS
from . import method
from timing import MethodBudget


def budget():
    return MethodBudget(300, clock=FakeClock())


def multiple_edges_fixture():
    return artificial([
        dict(id='a',unit='NPU0',opp='H',duration_H='2',duration_L='3',start='2',activity_H='5'),
        dict(id='b',unit='NPU0',opp='H',duration_H='2',duration_L='6',start='0',activity_H='5'),
        dict(id='x',unit='CPU2',opp='L',duration='1',start='2'),
        dict(id='v',unit='CPU1',opp='H',duration='1',start='3',deadline='8'),
        dict(id='u',unit='CPU1',opp='L',duration='1',start='5',deadline='8')],
        dependencies=[('b','x'),('a','u')])


class PrefilterTests(unittest.TestCase):
    def guard(self, ins, inc):
        return RoundFilter(ins, inc, budget(), new_counts())

    def test_first_rejected_edge_does_not_remove_second_legal_repair(self):
        ins, inc = multiple_edges_fixture()
        self.assertTrue(independent_legality(ins, inc))
        guard = self.guard(ins, inc)
        bounds, cert = guard.group('S0',['a','b'],{'a':'L','b':'L'},'reverse','earliest')
        self.assertIsNone(cert)
        args = (ins, inc, 'S0', ['a','b'], {'a':'L','b':'L'})
        base = core.reconstruct(*args, orientation='reverse')
        self.assertEqual(core.blocking_edges(base), [('v','u'),('x','v')])
        self.assertEqual(guard.edge(bounds,base,('v','u'))['kind'],'UNCHANGED_LATE_PATH')
        self.assertIsNone(guard.edge(bounds,base,('x','v')))
        repaired = core.reconstruct(*args,orientation='reverse',extra_resource_edge=('x','v'))
        self.assertEqual(repaired['state'],'COMPLETE_LEGAL_CANDIDATE')
        self.assertTrue(independent_legality(ins,repaired['candidate']))
        expected = list(ORIGINAL_PACKETS(ins,inc,budget()))
        diagnostics=[]
        actual = list(candidate_packets(ins,inc,budget(),diagnostics=diagnostics))
        self.assertEqual(actual,expected)
        self.assertTrue(any(d.get('prefilter_certificate',{}).get('kind')=='UNCHANGED_LATE_PATH' for d in diagnostics))

    def test_task_comparability_requires_actual_new_resource_edge(self):
        ins,inc=artificial([dict(id='a',unit='CPU1',duration='1',opp='H'),
            dict(id='b',unit='CPU2',duration='1',start='1',opp='H')],dependencies=[('a','b')])
        g=self.guard(ins,inc)
        self.assertIsNone(g.group('S0',['a','b'],{},'reverse','earliest')[1])
        self.assertEqual(g.group('S0',['a','b'],{'a':'L'},'reverse','earliest')[1]['kind'],
                         'PRIMARY_TASK_RESOURCE_CYCLE')
        legal=core.reconstruct(ins,inc,'S0',['a','b'],{},orientation='reverse')
        self.assertEqual(legal['state'],'COMPLETE_LEGAL_CANDIDATE')

    def test_time_bound_equality_is_not_rejected_and_exact_fraction_rounds(self):
        ins,inc=artificial([dict(id='a',unit='CPU1',opp='H',duration_H='1',duration_L='5/2'),
            dict(id='b',unit='NPU0',duration='1',start='2',deadline='4')],dependencies=[('a','b')],window='6')
        g=self.guard(ins,inc);bound,cert=g.group('S0',['a'],{'a':'L'},'incumbent','earliest')
        self.assertIsNone(cert);self.assertEqual(bound['earliest']['b'],3)
        self.assertEqual(bound['latest']['b'],3)
        ins['scenarios'][0]['requests'][1]['deadline_ms']='7/2'
        self.assertIsNotNone(self.guard(ins,inc).group('S0',['a'],{'a':'L'},'incumbent','earliest')[1])

    def test_explicit_start_subset_uses_its_own_next_and_previous(self):
        ins,inc=artificial([dict(id='a',unit='CPU1',opp='H',duration_H='1',duration_L='5/2'),
            dict(id='b',unit='NPU0',duration='1',start='2',deadline='5')],dependencies=[('a','b')],window='6')
        ins['start_domain']={'version':1,'kind':'explicit_grid_subset',
            'by_scene_stage_ms':{'S0':{'a':['0'],'b':['1','2','4']}}}
        b,c=self.guard(ins,inc).group('S0',['a'],{'a':'L'},'incumbent','earliest')
        self.assertIsNone(c);self.assertEqual(b['earliest']['b'],4)
        ins['start_domain']['by_scene_stage_ms']['S0']['b']=['1','2']
        self.assertIsNotNone(self.guard(ins,inc).group('S0',['a'],{'a':'L'},'incumbent','earliest')[1])

    def test_preserve_floor_cannot_contaminate_earliest_cache(self):
        ins,inc=artificial([dict(id='x',unit='GPU0',start='5',duration='2'),
            dict(id='y',unit='CPU1',start='7',opp='H',duration_H='1',duration_L='4',deadline='8')],
            dependencies=[('x','y')])
        g=self.guard(ins,inc)
        self.assertIsNotNone(g.group('S0',['y'],{'y':'L'},'incumbent','preserve')[1])
        self.assertIsNone(g.group('S0',['y'],{'y':'L'},'incumbent','earliest')[1])

    def test_small_grid_independent_oracle_for_time_bound_rejections(self):
        # Enumerate every start vector on three invented 0..6 ms grids.
        checks=0
        for deadline,low_duration in product(('3','4','5'),('2','5/2','4')):
            ins,inc=artificial([dict(id='a',unit='CPU1',opp='H',duration_H='1',duration_L=low_duration),
                dict(id='b',unit='NPU0',duration='1',start='1',deadline=deadline),
                dict(id='c',unit='GPU0',duration='1',start='2')],dependencies=[('a','b'),('b','c')],window='6')
            for template in ('earliest','preserve'):
                g=self.guard(ins,inc);bounds,cert=g.group('S0',['a'],{'a':'L'},'incumbent',template)
                legal=[]
                for starts in product(range(7),repeat=3):
                    trial=deepcopy(inc)
                    for row,t in zip(trial['scenes']['S0'],starts):row['start_ms']=str(t)
                    rows(trial)['a']['opp']='L'
                    if independent_legality(ins,trial):legal.append(starts)
                if cert is not None:self.assertFalse(legal)
                for times in legal:
                    for node,t in zip(('a','b','c'),times):
                        self.assertLessEqual(bounds['earliest'][node],t)
                        self.assertGreaterEqual(bounds['latest'][node],t)
                checks+=1
        self.assertEqual(checks,18)

    def test_complete_legal_packet_sequence_including_two_scenes_and_off(self):
        cases=[crossing_fixture(second_scene=True),multiple_edges_fixture(),crossing_input()[1:]]
        for ins,inc in cases:
            before=deepcopy((ins,inc))
            for enabled in (False,True):
                old=list(ORIGINAL_PACKETS(ins,inc,budget(),allow_blocking_edges=enabled))
                new=list(candidate_packets(ins,inc,budget(),allow_blocking_edges=enabled))
                self.assertEqual(new,old)
                disabled=list(candidate_packets(ins,inc,budget(),allow_blocking_edges=enabled,prefilter_enabled=False))
                self.assertEqual(disabled,old)
            self.assertEqual(before,(ins,inc))

    def test_expiry_is_not_reclassified_as_infeasibility(self):
        ins,inc=crossing_fixture();clock=FakeClock();b=MethodBudget(300,clock=clock)
        g=RoundFilter(ins,inc,b,new_counts());clock.now=b.deadline
        from thermal import Exhausted
        with self.assertRaises(Exhausted):g.group('S0',['a'],{'a':'L'},'incumbent','earliest')

    def test_frozen_lifecycle_same_mock_evaluation_and_acceptance_path(self):
        config,ins,inc=crossing_input();parent=(RESEARCH.parent/'.runtime').resolve();parent.mkdir(exist_ok=True)
        saved={n:getattr(frozen,n) for n in ('candidate_packets','source_identity','RULE_VERSION','RULES','execute_reconstruction')}
        outcomes=[]
        with tempfile.TemporaryDirectory(prefix='onp-correctness-',dir=parent) as tmp:
            for arm in ('old','new'):
                clock=FakeClock();seen=[]
                def initialize(i,c,b,assess,**kw):
                    assess(deepcopy(inc),'mock:initial');return {'status':'MOCK_INITIALIZER_COMPLETED'}
                def evaluate(i,c,a,b):
                    clock.now+=1;seen.append(frozen.digest(c))
                    energy='100' if len(seen)==1 else '50'
                    return complete_mock(i,c,a,b,interval=(energy,energy))
                with patch('thermal.evaluate_candidate',side_effect=AssertionError('NO_REAL_THERMAL')), \
                     patch('heft_method.run_heft',side_effect=AssertionError('NO_REAL_HEFT')):
                    fn=frozen.execute_reconstruction if arm=='old' else method.execute_reconstruction
                    r=fn(lambda b:(deepcopy(config),deepcopy(ins)),Path(tmp)/arm,
                        bindings=frozen.Bindings(initialize,evaluate),clock=clock)
                self.assertFalse(r['usable_as_research_evidence'])
                outcomes.append((seen,r['safe_candidate'],[p['strict_accepted'] for p in r['graph_proposals']]))
        self.assertEqual(*outcomes)
        for n,v in saved.items():self.assertIs(getattr(frozen,n),v)


if __name__=='__main__':unittest.main()
