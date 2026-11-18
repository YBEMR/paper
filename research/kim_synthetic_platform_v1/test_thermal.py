"""Analytic and independent-oracle checks on deliberately small power fixtures."""
import unittest

import numpy as np
from scipy.linalg import expm

from thermal import evaluate_thermal


class ThermalTests(unittest.TestCase):
    def setUp(self):
        self.args = dict(capacity_J_K=[2,2,2,2], conductance_W_K=np.eye(4),
                         idle_W=[0,0,0,0], slope_W_K=[0,0,0,0],
                         board_W=0.0, board_heat_fraction=[0]*4,
                         ambient_C=25, reference_C=25, initial_C=[25]*4,
                         limits_C=[80]*4)
        self.pulse = [[4,0,0,0]]

    def simulate(self, dt, act, **updates):
        return evaluate_thermal(dt, act, **(self.args | updates))

    def test_zero_load_stays_at_ambient(self):
        r = self.simulate([10],np.zeros((1,4)))
        np.testing.assert_allclose(r["final_C"],25)
        self.assertEqual(r["energy_J"],0)
        self.assertEqual(r["thermal_status"],"SAFE")

    def test_exact_single_node_constant_power_with_leakage(self):
        # C*x'=-0.8*x+4 => x=5(1-exp(-0.4t)), x=T-25.
        r = self.simulate([2],self.pulse,slope_W_K=[.2,0,0,0])
        expected_T = 25+5*(1-np.exp(-.8))
        expected_J = 8 + .2*5*(2 - (1-np.exp(-.8))/.4)
        self.assertAlmostEqual(r["final_C"][0],expected_T,11)
        self.assertAlmostEqual(r["energy_J"],expected_J,11)
        self.assertLessEqual(r["peak_lower_C"][0],expected_T)
        self.assertGreaterEqual(r["peak_upper_C"][0],expected_T)

    def test_transfer_and_board_counted_once(self):
        # A portion heats modeled nodes; the entire common and transfer loads
        # (including the portion external to the RC model) enter board energy.
        r = self.simulate([1],self.pulse,idle_W=[.5]*4,board_W=2,
                          board_heat_fraction=[.25,0,0,0],
                          transfer_W=[3],transfer_heat_fraction=[0,0,.5,0])
        self.assertEqual(r["energy_J"],11)
        self.assertEqual(r["transfer_J"],3)
        np.testing.assert_allclose(r["final_C"],25+(1-np.exp(-.5))*np.array([5,.5,2,.5]),
                                   atol=2e-12,rtol=0)

    def test_continuity_and_independent_reset(self):
        args = dict(slope_W_K=[.25,0,0,0])
        dt,act = [1,1],[self.pulse[0], [0]*4]
        whole = self.simulate(dt,act,**args)
        one = self.simulate(dt[:1],act[:1],**args)
        two = self.simulate(dt[1:],act[1:],initial_C=one["final_C"],**args)
        reset = self.simulate(dt,act,reset_indices=[1],trace=True,**args)
        np.testing.assert_allclose(whole["final_C"],two["final_C"],atol=1e-13,rtol=0)
        self.assertAlmostEqual(whole["energy_J"],one["energy_J"]+two["energy_J"],12)
        self.assertGreater(whole["energy_J"],reset["energy_J"])
        np.testing.assert_allclose(reset["final_C"],25)
        np.testing.assert_allclose(reset["trace_time_s"],[0,1,1,2])
        np.testing.assert_allclose(reset["trace_C"][2],25)

    def test_no_leakage_removes_energy_history_but_not_temperature_history(self):
        dt,act = [1,1],[self.pulse[0],[0]*4]
        a = self.simulate(dt,act)
        b = self.simulate(dt,act,reset_indices=[1])
        self.assertEqual(a["energy_J"],b["energy_J"])
        self.assertGreater(a["final_C"][0],b["final_C"][0])

    def test_separate_dlas_warm_and_exchange_heat(self):
        g = np.eye(4)
        g[2:4,2:4] = [[2,-1],[-1,2]]
        r = self.simulate([1],[[0,0,4,0]],conductance_W_K=g)
        self.assertGreater(r["final_C"][2],r["final_C"][3])
        self.assertGreater(r["final_C"][3],25)
        self.assertAlmostEqual(r["final_C"][0],25)

    def test_hidden_continuous_peak_with_safe_endpoints(self):
        g = np.array([[2,-1,0,0],[-1,2,0,0],[0,0,1,0],[0,0,0,1]])
        initial = [25,45,25,25]
        r = self.simulate([8],np.zeros((1,4)),conductance_W_K=g,initial_C=initial,
                          limits_C=[28,80,80,80],capacity_J_K=[1]*4)
        # Exact first node is 25+10*(exp(-t)-exp(-3t)); endpoints < 28.
        t_peak = np.log(3)/2
        peak = 25+10*(np.exp(-t_peak)-np.exp(-3*t_peak))
        self.assertLess(max(initial[0],r["final_C"][0]),28)
        self.assertGreater(r["peak_lower_C"][0],28)
        self.assertLessEqual(r["peak_lower_C"][0],peak)
        self.assertGreaterEqual(r["peak_upper_C"][0],peak)
        self.assertLess(r["peak_upper_C"][0]-r["peak_lower_C"][0],5.1e-4)
        self.assertEqual(r["thermal_status"],"VIOLATION")

    def test_against_augmented_matrix_exponential(self):
        # A 6-variable independent oracle integrates 4 absolute temperatures,
        # their scalar leakage energy, and affine forcing in one exponential.
        c = np.array([1.1,1.7,2.6,2.2])
        g = np.diag([1.4,1.1,.7,.7])
        g += np.diag([-.2,-.15,-.1],1)+np.diag([-.2,-.15,-.1],-1)
        slopes = np.array([.02,.08,.05,.06])
        x = np.array([32.,37.,41.,30.])
        act = np.array([[0,1.7,.3,1.1],[.8,0,2,0],[0,1,0,1.]])
        dt = [.16,1.24,.07]
        r = self.simulate(dt,act,conductance_W_K=g,capacity_J_K=c,
                          slope_W_K=slopes,initial_C=x,ambient_C=30)
        y = np.r_[x,0,1]
        for h,power in zip(dt,act):
            a = np.zeros((6,6))
            a[:4,:4] = (np.diag(slopes)-g)/c[:,None]
            a[:4,5] = (power + g.sum(axis=1)*30 - slopes*25)/c
            a[4,:4] = slopes
            a[4,5] = np.sum(power-slopes*25)
            y = expm(a*h) @ y
        np.testing.assert_allclose(r["final_C"],y[:4],rtol=0,atol=1e-11)
        self.assertAlmostEqual(r["energy_J"],y[4],11)

    def test_unstable_or_nonpassive_model_rejected(self):
        with self.assertRaises(ValueError):
            self.simulate([1],self.pulse,slope_W_K=[1.1,0,0,0])
        with self.assertRaises(ValueError):
            self.simulate([1],self.pulse,conductance_W_K=-np.eye(4))

    def test_equality_is_explicitly_unresolved_at_guard_precision(self):
        r = self.simulate([1],np.zeros((1,4)),limits_C=[25]*4)
        self.assertEqual(r["thermal_status"],"UNRESOLVED")


if __name__ == "__main__":
    unittest.main()
