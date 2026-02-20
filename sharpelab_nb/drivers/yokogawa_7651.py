"""QCoDeS driver for the Yokogawa 7651 programmable DC source."""

from __future__ import annotations

import time
from typing import Any

from qcodes.instrument import VisaInstrument
from qcodes.validators import Bool, Enum, Numbers


class Yokogawa7651(VisaInstrument):
    """
    QCoDeS driver for the Yokogawa 7651 programmable DC source.

    The 7651 is pre-SCPI and does not support ``*IDN?``.  Many
    models/firmware cannot query programmed voltage, current, or mode
    over the bus, so those parameters are write-only with software
    caching.

    After changing mode, level, or output the instrument is triggered
    with ``E;`` so that changes take effect immediately.

    Parameters
    ----------
    name : str
        Instrument name.
    address : str
        VISA resource address.
    coil_constant : float | None
        Coil constant in T/A.  When provided, a ``field`` parameter
        (Tesla) is added that converts to current automatically.
        QCoDeS ``step``/``inter_delay`` are pre-configured on it for
        safe ramping.
    **kwargs
        Forwarded to ``VisaInstrument.__init__``.
    """

    # The 7651 is pre-SCPI — commands are terminated with ';' which we
    # include explicitly in each command string.  Tell VISA not to add
    # its own terminator on either direction.
    default_terminator: str | None = ""

    def __init__(
        self,
        name: str,
        address: str,
        *,
        coil_constant: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(name, address, **kwargs)

        # Software caches for non-queryable settings.
        self._mode_cache: str | None = None  # "VOLT" or "CURR"
        self._voltage_cache: float | None = None
        self._current_cache: float | None = None
        self._output_cache: bool | None = None
        self._coil_constant: float | None = coil_constant

        self.add_parameter(
            "mode",
            label="Source mode",
            vals=Enum("VOLT", "CURR"),
            get_cmd=None,
            set_cmd=self._set_mode,
            docstring=(
                "Source mode. 'VOLT' uses F1;, 'CURR' uses F5;. "
                "Write-only; cached in software."
            ),
        )

        self.add_parameter(
            "volt",
            label="Output voltage",
            unit="V",
            vals=Numbers(-30, 30),
            get_cmd=None,
            set_cmd=self._set_voltage,
        )

        self.add_parameter(
            "current",
            label="Output current",
            unit="A",
            vals=Numbers(-0.12, 0.12),
            get_cmd=None,
            set_cmd=self._set_current,
        )

        if self._coil_constant is not None:
            max_I = 0.12  # A
            max_B = max_I * abs(self._coil_constant)
            field_vals: Numbers | None = Numbers(-max_B, max_B)
        else:
            field_vals = None

        self.add_parameter(
            "field",
            label="Magnetic field",
            unit="T",
            vals=field_vals,
            get_cmd=None,
            set_cmd=self._set_field,
        )

        if self._coil_constant is not None:
            self.field.step = 0.0001  # T
            self.field.inter_delay = 0.1  # s  → ~1 mT/s

        self.add_parameter(
            "output",
            label="Output enable",
            vals=Bool(),
            get_cmd=None,
            set_cmd=self._set_output,
        )

        self.connect_message()

    # --- Cache management --------------------------------------------------

    def set_voltage_cache(self, value: float) -> None:
        """Manually seed the voltage cache (e.g. after a kernel restart)."""
        self._voltage_cache = value

    def set_current_cache(self, value: float) -> None:
        """Manually seed the current cache (e.g. after a kernel restart)."""
        self._current_cache = value

    # --- Low-level helpers -------------------------------------------------

    def write_cmd(self, cmd: str) -> None:
        """Send a raw command string (must include its ``;`` terminator)."""
        self.write(cmd)

    def trigger(self) -> None:
        """Send ``E;`` — the 7651 requires this after parameter changes."""
        self.write_cmd("E;")

    # --- IDN handling ------------------------------------------------------

    def get_idn(self) -> dict[str, str | None]:
        """Return a static IDN dict (the 7651 does not support ``*IDN?``)."""
        return {
            "vendor": "YOKOGAWA",
            "model": "7651",
            "serial": None,
            "firmware": None,
        }

    # --- Parameter setters -------------------------------------------------

    def _set_mode(self, mode: str) -> None:
        mode = mode.upper()
        if mode == "VOLT":
            self.write_cmd("F1;")
        elif mode == "CURR":
            self.write_cmd("F5;")
        else:
            raise ValueError(f"Unsupported mode {mode!r}; use 'VOLT' or 'CURR'.")
        self.trigger()
        self._mode_cache = mode

    def _set_voltage(self, value: float) -> None:
        if self._mode_cache != "VOLT":
            self._set_mode("VOLT")
        self.write_cmd(f"SA{value:.6f};")
        self.trigger()
        self._voltage_cache = value

    def _set_current(self, value: float) -> None:
        if self._mode_cache != "CURR":
            self._set_mode("CURR")
        self.write_cmd(f"SA{value:.6f};")
        self.trigger()
        self._current_cache = value

    def _set_field(self, field: float) -> None:
        if self._coil_constant is None:
            raise RuntimeError(
                "No coil_constant set — pass coil_constant= to "
                "Yokogawa7651.__init__ to use the field parameter."
            )
        if self._mode_cache != "CURR":
            self._set_mode("CURR")
        value = field / self._coil_constant
        self.write_cmd(f"SA{value:.6f};")
        self.trigger()
        self._current_cache = value

    def _set_output(self, state: bool) -> None:
        self.write_cmd("O1;" if state else "O0;")
        self.trigger()
        self._output_cache = bool(state)

    # --- Convenience ramp methods -----------------------------------------

    def _resolve_start(
        self,
        cache: float | None,
        start: float | None,
        label: str,
    ) -> float:
        """Return the starting value for a ramp, or raise if unknowable."""
        if start is not None:
            return start
        if cache is not None:
            return cache
        raise RuntimeError(
            f"Yokogawa7651: {label} cache is empty (kernel restart?) and no "
            f"explicit `start` was given.  Either call "
            f"`set_{label}_cache(<actual value>)` first or pass `start=`."
        )

    def ramp_voltage(
        self,
        target: float,
        step: float = 0.01,
        delay: float = 0.05,
        start: float | None = None,
    ) -> None:
        """
        Software ramp of voltage from *start* (or cached value) to *target*.

        Parameters
        ----------
        target : float
            Target voltage in volts.
        step : float
            Step size in volts (must be > 0).
        delay : float
            Delay between steps in seconds.
        start : float | None
            Explicit starting voltage.  Required when the software cache
            is empty (e.g. after a kernel restart).
        """
        if step <= 0:
            raise ValueError("step must be > 0")

        v = self._resolve_start(self._voltage_cache, start, "voltage")

        direction = 1 if target >= v else -1
        step_signed = step * direction

        while (direction > 0 and v < target) or (direction < 0 and v > target):
            v_next = v + step_signed
            if (direction > 0 and v_next > target) or (
                direction < 0 and v_next < target
            ):
                v_next = target
            self.volt(v_next)
            time.sleep(delay)
            v = v_next

    def ramp_current(
        self,
        target: float,
        step: float = 0.001,
        delay: float = 0.05,
        start: float | None = None,
    ) -> None:
        """
        Software ramp of current from *start* (or cached value) to *target*.

        Parameters
        ----------
        target : float
            Target current in amps.
        step : float
            Step size in amps (must be > 0).
        delay : float
            Delay between steps in seconds.
        start : float | None
            Explicit starting current.  Required when the software cache
            is empty (e.g. after a kernel restart).
        """
        if step <= 0:
            raise ValueError("step must be > 0")

        i = self._resolve_start(self._current_cache, start, "current")

        direction = 1 if target >= i else -1
        step_signed = step * direction

        while (direction > 0 and i < target) or (direction < 0 and i > target):
            i_next = i + step_signed
            if (direction > 0 and i_next > target) or (
                direction < 0 and i_next < target
            ):
                i_next = target
            self.current(i_next)
            time.sleep(delay)
            i = i_next
