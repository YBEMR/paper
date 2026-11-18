import unittest
from collections import Counter
from workloads import CONFIG, FROZEN, conditions, time_ns, workload


class ProtocolChecks(unittest.TestCase):
    def test_full_design(self):
        cases = list(conditions())
        self.assertEqual(len({c["case_id"] for c in cases}), 40)
        self.assertEqual(Counter(c["variation"] for c in cases), {"base":36, "r080":2, "r120":2})
        self.assertEqual(CONFIG["order"], FROZEN["fsm"]["trace"])

    def test_short_regresses_to_freeze(self):
        for fps in CONFIG["fps"]:
            req, changes, end = workload("short", fps)
            orig = FROZEN["workload"]["requests"]
            self.assertEqual([(r.app,r.release_ns,r.deadline_ns) for r in req],
                [(r["app"],time_ns(r["release_period"],fps),time_ns(r["deadline_period"],fps)) for r in orig])
            self.assertEqual(end,time_ns(5,fps))
            self.assertEqual([scene for _,scene in changes],CONFIG["order"])

    def test_exact_repeated_service_and_common_tail(self):
        for fps in CONFIG["fps"]:
            a, switch, end = workload("10s",fps)
            b, s2, end2 = workload("20s",fps)
            self.assertEqual(len(b),2*len(a))
            self.assertEqual(b[:len(a)],a)
            for x,y in zip(a,b[len(a):]):
                self.assertEqual((x.app,x.release_ns+10**10,x.deadline_ns+10**10),(y.app,y.release_ns,y.deadline_ns))
            self.assertEqual(s2,switch+[(t+10**10,s) for t,s in switch])
            self.assertEqual(end2-end,10**10)
            self.assertEqual(max(q.deadline_ns for q in b),2*10**10)
            self.assertEqual(len(set(r.id for r in b)),len(b))
            self.assertEqual(end-10**10,time_ns(1,fps))
