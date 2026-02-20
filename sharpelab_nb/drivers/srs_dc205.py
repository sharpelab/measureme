"""QCoDeS driver for the SRS DC205 precision DC voltage source."""

from __future__ import annotations

import time
from typing import Any

import numpy as np
import qcodes
from qcodes.validators import Ints


class SRS_DC205(qcodes.VisaInstrument):
    """
    QCoDeS driver for the Stanford Research Systems DC205 DC voltage source.

    Parameters
    ----------
    name : str
        Instrument name.
    address : str
        VISA resource address.
    ramp_num_points : int
        Number of interpolation points for ``smart_voltage`` ramps.
    ramp_wait_time : float
        Delay in seconds between ramp steps.
    **kwargs
        Forwarded to ``VisaInstrument.__init__``.
    """

    def __init__(
        self,
        name: str,
        address: str,
        *,
        ramp_num_points: int = 100,
        ramp_wait_time: float = 0.01,
        **kwargs: Any,
    ) -> None:
        super().__init__(name, address, terminator="\r\n", **kwargs)

        self.add_parameter(
            "output",
            get_cmd="SOUT?",
            get_parser=int,
            set_cmd="SOUT {}",
        )
        self.add_parameter(
            "voltage",
            label="Voltage",
            unit="V",
            get_cmd="VOLT?",
            get_parser=float,
            set_cmd="VOLT {:.7f}",
        )
        self.add_parameter(
            "voltage_range",
            label="Voltage Range",
            unit="V",
            get_cmd="RNGE?",
            get_parser=int,
            set_cmd="RNGE {}",
            vals=Ints(0, 2),
            docstring="0: +/-1 V, 1: +/-10 V, 2: +/-100 V",
        )
        self.add_parameter(
            "smart_voltage",
            label="smart voltage",
            unit="V",
            get_cmd="VOLT?",
            get_parser=float,
            set_cmd=self.ramp_voltage,
        )

        self.visa_handle.baud_rate = 115200  # type: ignore[attr-defined]  # serial resource attr
        self.ramp_num_points: int = ramp_num_points
        self.ramp_wait_time: float = ramp_wait_time
        self.connect_message()

    def ramp_voltage(self, volt: float) -> None:
        """Ramp to *volt* from the current voltage reading."""
        starting_volt: float = self.voltage()
        voltage_vec = np.linspace(starting_volt, volt, self.ramp_num_points)
        for v in voltage_vec:
            # The instrument rejects numbers with too many decimal places.
            self.voltage(np.round(v, 9))
            time.sleep(self.ramp_wait_time)

        # The DC205 needs extra settling time after large voltage changes.
        if abs(volt - starting_volt) > 0.1:
            time.sleep(10)
