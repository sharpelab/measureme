import unittest

from qcodes.instrument_drivers.mock_instruments import DummyInstrument

from sharpelab_nb.status import Status


class TestStatus(unittest.TestCase):
    def setUp(self) -> None:
        self.dac = DummyInstrument("dac", gates=["ch1", "ch2"])
        self.dac.ch1(1.5)
        self.dac.ch2(3.0)

    def tearDown(self) -> None:
        self.dac.close()

    def test_reads_current_values(self) -> None:
        status = Status(V1=self.dac.ch1, V2=self.dac.ch2)
        result = status()
        self.assertAlmostEqual(result["V1"], 1.5)
        self.assertAlmostEqual(result["V2"], 3.0)

    def test_reflects_changes(self) -> None:
        status = Status(V1=self.dac.ch1)
        self.assertAlmostEqual(status()["V1"], 1.5)
        self.dac.ch1(9.9)
        self.assertAlmostEqual(status()["V1"], 9.9)

    def test_repr(self) -> None:
        status = Status(V1=self.dac.ch1)
        self.assertIn("V1", repr(status))


if __name__ == "__main__":
    unittest.main()
