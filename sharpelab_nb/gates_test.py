import unittest

import numpy as np

from sharpelab_nb.gates import calculate_gate_voltages, calculate_n_D, comment_to_gates


class TestGateConversions(unittest.TestCase):
    def test_roundtrip(self) -> None:
        """(n, D) -> (Vtg, Vbg) -> (n, D) should be identity."""
        n_in, D_in = 1e12, 0.5
        Vtg, Vbg = calculate_gate_voltages(n_in, D_in)
        n_out, D_out = calculate_n_D(Vtg, Vbg)
        self.assertAlmostEqual(float(n_out), n_in, places=3)
        self.assertAlmostEqual(float(D_out), D_in, places=3)

    def test_zero(self) -> None:
        Vtg, Vbg = calculate_gate_voltages(0, 0)
        self.assertAlmostEqual(float(Vtg), 0)
        self.assertAlmostEqual(float(Vbg), 0)

    def test_arrays(self) -> None:
        n = np.array([0, 1e12, 2e12])
        D = np.array([0, 0.5, 1.0])
        Vtg, Vbg = calculate_gate_voltages(n, D)
        n_out, D_out = calculate_n_D(Vtg, Vbg)
        np.testing.assert_allclose(n_out, n, rtol=1e-5)
        np.testing.assert_allclose(D_out, D, rtol=1e-5)

    def test_custom_geometry(self) -> None:
        """Different dielectric thicknesses should change the result."""
        Vtg1, Vbg1 = calculate_gate_voltages(1e12, 0.5, dtg=16, dbg=25.5)
        Vtg2, Vbg2 = calculate_gate_voltages(1e12, 0.5, dtg=30, dbg=300)
        self.assertNotAlmostEqual(float(Vtg1), float(Vtg2))
        self.assertNotAlmostEqual(float(Vbg1), float(Vbg2))


class TestCommentToGates(unittest.TestCase):
    def test_basic(self) -> None:
        Vtg, Vbg = comment_to_gates("nD point: (3.5, -2.1)")
        self.assertAlmostEqual(Vtg, 3.5)
        self.assertAlmostEqual(Vbg, -2.1)

    def test_no_key(self) -> None:
        Vtg, Vbg = comment_to_gates("(1.0, 2.0)", delim=":")
        self.assertAlmostEqual(Vtg, 1.0)
        self.assertAlmostEqual(Vbg, 2.0)


if __name__ == "__main__":
    unittest.main()
