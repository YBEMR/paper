"""Physical-screen regression using toy segments only."""
import unittest

import numpy as np

from joint_thermal import SAFE, VIOLATION, UNRESOLVED, compile_scene


def physics(**overrides):
    base = dict(capacity_J_K=[1.2,1.4,0.8,1.6], conductance_W_K=np.eye(4),
                idle_W=[0.3,0.4,0.15,0.15], slope_W_K=[0.04,0.03,0.02,0.02],
                board_W=0.4, board_heat_fraction=[0,0,0,0], transfer_heat_fraction=[0.25]*4,
                ambient_C=25, reference_C=25, initial_C=[30]*4, limits_C=[36]*4)
    return base | overrides


class JointThermalTests(unittest.TestCase):
    def test_varying_inlets_match_direct_thermal_reference(self):
        rng = np.random.default_rng(519)
        dt = rng.uniform(.001,.05,120)
        activity = rng.uniform(0,12,(len(dt),4))
        transfer = rng.uniform(0,.6,len(dt))
        g = np.diag([1.25,1.75,1.5,1.8]) + np.diag([-.3,-.15,-.25],1) + np.diag([-.3,-.15,-.25],-1)
        k = compile_scene(dt,activity,transfer,physics(conductance_W_K=g))
        states = rng.uniform(25,38,(200,4))
        energy, end, status = k.batch(states)
        labels = {"SAFE":SAFE, "VIOLATION":VIOLATION, "UNRESOLVED":UNRESOLVED}
        for index, inlet in enumerate(states):
            reference = k.replay(inlet)
            np.testing.assert_allclose(end[index],reference["final_C"],rtol=0,atol=1e-10)
            self.assertAlmostEqual(energy[index],reference["energy_J"],10)
            self.assertEqual(status[index],labels[reference["thermal_status"]])
        self.assertIn(SAFE, status)
        self.assertIn(VIOLATION, status)

    def test_safe_endpoints_can_hide_violation(self):
        g = np.eye(4)
        g[:2,:2] = [[2,-1],[-1,2]]
        kw = physics(conductance_W_K=g,idle_W=[0]*4,slope_W_K=[0]*4,initial_C=[25]*4,
                     capacity_J_K=[1]*4,limits_C=[28,80,80,80])
        k = compile_scene([8],np.zeros((1,4)),[0],kw)
        _, final, status = k.batch([[25,45,25,25], [25,26,25,25]])
        self.assertLess(final[0,0],28)
        self.assertEqual(list(status),[VIOLATION, SAFE])

    def test_ambiguous_limit_matches_reference(self):
        kw = physics(initial_C=[25]*4,limits_C=[25]*4,idle_W=[0]*4,slope_W_K=[0]*4)
        k = compile_scene([1],np.zeros((1,4)),[0],kw)
        _, _, status = k.batch([[25]*4])
        self.assertEqual(status[0],UNRESOLVED)
        self.assertEqual(k.fallback_calls,1)

    def test_boundary_composition_is_additive(self):
        kw = physics()
        dt = np.array([.05,.5,.123,1.2])
        active = np.eye(4)*4
        tr = np.array([1.,.5,0,.5])
        a = compile_scene(dt[:2],active[:2],tr[:2],kw)
        b = compile_scene(dt[2:],active[2:],tr[2:],kw)
        whole = compile_scene(dt,active,tr,kw)
        ta = np.array([[29.,30.,34.,27.],[30.,31.,33.,30.]])
        e1,t1,s1 = a.batch(ta)
        e2,t2,s2 = b.batch(t1)
        e,t,s = whole.batch(ta)
        np.testing.assert_allclose(e1+e2,e,rtol=0,atol=1e-10)
        np.testing.assert_allclose(t2,t,rtol=0,atol=1e-10)
        np.testing.assert_array_equal(s, np.minimum(s1,s2))

    def test_above_reference_domain(self):
        k = compile_scene([.1],np.zeros((1,4)),[0.],physics())
        with self.assertRaises(ValueError):
            k.batch([[24.,30.,30.,30.]])


if __name__ == "__main__":
    unittest.main()
