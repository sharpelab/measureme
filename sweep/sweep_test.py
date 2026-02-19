import tempfile
import unittest
from typing import cast

from qcodes.instrument_drivers.mock_instruments import DummyInstrument

import sweep
import sweep.db as db
from sweep.types import SweepMetadata


class TestStation(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.dac = DummyInstrument("dac", gates=["ch1", "ch2", "ch3"])

    def tearDown(self) -> None:
        self.dac.close()
        self.dir.cleanup()

    def test_measure(self) -> None:
        self.dac.ch1(1.0)
        self.dac.ch2(2.0)
        s = sweep.Station(basedir=self.dir.name, verbose=True)
        s.fp(self.dac.ch1).fp(self.dac.ch2)
        res = s.measure()
        with db.Reader(res.basedir, res.id) as r:
            self.assertEqual(r.metadata["type"], "0D")
            self.assertEqual(r.metadata["columns"][0], "time")
            self.assertEqual(r.metadata["columns"][1], "dac_ch1")
            self.assertEqual(len(r.all_data()), 1)
            self.assertEqual(float(r.all_data()[0][1]), 1.0)

    def test_sweep(self) -> None:
        self.dac.ch2(1.0)
        self.dac.ch3(2.0)
        s = sweep.Station(basedir=self.dir.name, verbose=True)
        s.fp(self.dac.ch2).fp(self.dac.ch3)
        res = s.sweep(self.dac.ch1, range(100))
        with db.Reader(res.basedir, res.id) as r:
            md = cast(SweepMetadata, r.metadata)
            self.assertEqual(md["type"], "1D")
            self.assertEqual(md["param"], "dac_ch1")
            self.assertEqual(md["columns"][0], "time")
            self.assertEqual(md["columns"][1], "dac_ch1")
            self.assertEqual(md["columns"][2], "dac_ch2")
            self.assertEqual(md["columns"][3], "dac_ch3")
            self.assertEqual(len(r.all_data()), 100)

    def test_sweep_plot(self) -> None:
        self.dac.ch2(1.0)
        self.dac.ch3(2.0)
        s = sweep.Station(basedir=self.dir.name, verbose=True)
        s.fp(self.dac.ch2).fp(self.dac.ch3)
        s.plot("dac_ch1", "dac_ch2")
        res = s.sweep(self.dac.ch1, range(10))
        with db.Reader(res.basedir, res.id) as r:
            self.assertEqual(len(r.all_data()), 10)
            self.assertTrue(len(r.blob("plot.png")) > 0)


if __name__ == "__main__":
    unittest.main()
