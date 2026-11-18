"""Exact arithmetic tests of Case B's fixed-window identities; no simulator."""
from fractions import Fraction
import unittest


def weights(fps):
    if fps <= 0:
        raise ValueError("FPS must be positive")
    h = Fraction(1, fps)
    return (h, h, h, 2*h)


def gap_interval(independent_low, independent_high, correction_low, correction_high):
    """Interval for E_q-E_p. Correction means H_p-H_q, both in joules."""
    if independent_low > independent_high or correction_low > correction_high:
        raise ValueError("Unordered endpoints")
    return independent_low-correction_high, independent_high-correction_low


class CaseBBounds(unittest.TestCase):
    def test_five_and_four_cycles(self):
        for fps, ki, kh in ((20, Fraction(1,4), Fraction(1,5)),
                            (25, Fraction(1,5), Fraction(4,25)),
                            (30, Fraction(1,6), Fraction(2,15))):
            window = weights(fps)
            self.assertEqual(sum(window), ki)
            self.assertEqual(sum(window[1:]), kh)
            self.assertEqual(window[-1], 2*window[0])

    def test_thresholds_ten_millijoules(self):
        margin = Fraction(1,100)
        for fps, threshold in ((20,Fraction(1,20)), (25,Fraction(1,16)), (30,Fraction(3,40))):
            self.assertEqual(margin/sum(weights(fps)[1:]), threshold)

    def test_margin_interval_cases(self):
        self.assertEqual(gap_interval(9,11,3,7), (2,8))
        self.assertEqual(gap_interval(9,11,12,14), (-5,-1))
        self.assertEqual(gap_interval(9,11,8,12), (-3,3))
        self.assertEqual(gap_interval(10,10,10,10), (0,0))

    def test_correction_span_and_factor_two(self):
        kh = sum(weights(25)[1:])
        # Endpoint proof example with a shared 1..4 W interval. Opposing
        # continuous-minus-reset differences are possible without sign bounds.
        pos, neg = Fraction(4)-1, Fraction(1)-4
        self.assertEqual(kh*(pos-neg), 2*kh*(4-1))

    def test_different_weights_need_an_extra_term(self):
        # Scalar algebra at one segment, not a thermal or deployment model.
        wp, wq = Fraction(3,100), Fraction(1,100)
        tp, tq, reset = 56, 53, 50
        exact = wp*(tp-reset)-wq*(tq-reset)
        self.assertEqual(exact, wp*(tp-tq)+(wp-wq)*(tq-reset))
        self.assertNotEqual(exact, wp*(tp-tq))


if __name__ == "__main__":
    unittest.main()
