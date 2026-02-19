import unittest

from sharpelab_nb.config import (
    build_measurement_config,
    get_channels,
    get_contact_pairs,
)
from sharpelab_nb.types import label_for_role


MC = {
    "sr830_1": "28-25",
    "sr830_2": "25-24",
    "sr830_3": "24-21",
    "sr830_4": "I_{10-15}",
    "sr830_5": "11-13",
    "sr830_6": "13-14",
    "sr830_7": "25-11",
}

CP = {
    "curr": {"channels": [4]},
    "long1": {"channels": [1, 2]},
    "fakehall": {"channels": [3]},
    "realhall": {"channels": [5, 6]},
    "nl": {"channels": [7]},
}


class TestBuildMeasurementConfig(unittest.TestCase):
    def test_build_and_extract(self) -> None:
        config = build_measurement_config(MC, CP)
        self.assertTrue(config["__sharpelab__"])
        self.assertEqual(config["channels"], MC)

        pairs = get_contact_pairs(config)
        assert pairs is not None
        self.assertEqual(pairs["curr"]["channels"], [4])
        self.assertEqual(pairs["curr"]["contacts"], ["I_{10-15}"])
        self.assertEqual(pairs["long1"]["channels"], [1, 2])
        self.assertEqual(pairs["long1"]["contacts"], ["28-25", "25-24"])
        self.assertEqual(pairs["realhall"]["channels"], [5, 6])
        self.assertEqual(pairs["realhall"]["contacts"], ["11-13", "13-14"])

    def test_get_channels(self) -> None:
        config = build_measurement_config(MC, CP)
        channels = get_channels(config)
        self.assertEqual(channels, MC)

    def test_missing_channel_raises(self) -> None:
        bad_cp = {"bogus": {"channels": [99]}}
        with self.assertRaises(ValueError):
            build_measurement_config(MC, bad_cp)

    def test_no_sentinel_returns_none(self) -> None:
        plain_mc = {"sr830_1": "28-25"}
        self.assertIsNone(get_contact_pairs(plain_mc))
        self.assertIsNone(get_channels(plain_mc))


class TestLabelForRole(unittest.TestCase):
    def test_known_roles(self) -> None:
        self.assertIn("I", label_for_role("curr"))
        self.assertIn("R_{xx}", label_for_role("long1"))
        self.assertIn("R_{xx}", label_for_role("long2"))
        self.assertIn("R_{yx}", label_for_role("fakehall"))
        self.assertIn("R_{yx}", label_for_role("realhall"))
        self.assertIn("R_{NL}", label_for_role("nl"))

    def test_unknown_role_returns_name(self) -> None:
        self.assertEqual(label_for_role("mystery"), "mystery")


if __name__ == "__main__":
    unittest.main()
