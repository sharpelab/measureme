import time

import numpy as np


def autorange_sr830s(
    sr830_current: object,
    sr830s: list[object],
    lower_lim: float = 1e-6,
) -> None:
    """Auto-adjust SR830 sensitivity based on current reading vs. range.

    Checks the phase of the current-measuring SR830 to verify valid
    measurement conditions, then iterates through the other lock-ins
    and adjusts sensitivity up or down as needed.

    Waits 10x the time constant between sensitivity changes per the
    SR830 manual guidelines.

    Args:
        sr830_current: The SR830 instrument measuring current. Used for
            phase check only.
        sr830s: List of SR830 instruments to auto-range.
        lower_lim: Minimum sensitivity threshold. Won't decrement below this.
    """
    if len(sr830s) == 0:
        return

    p = sr830_current.P()  # type: ignore[union-attr]
    if np.abs(p) < 160:
        return

    for s in sr830s:

        def autorange_once(sr830: object) -> bool:
            r = sr830.R()  # type: ignore[union-attr]
            sens = sr830.sensitivity()  # type: ignore[union-attr]

            if r > 0.9 * sens:
                return sr830.increment_sensitivity()  # type: ignore[union-attr]
            elif r < 0.1 * sens:
                if sens <= lower_lim:
                    return False
                else:
                    return sr830.decrement_sensitivity()  # type: ignore[union-attr]
            return False

        adjustments = 0
        while autorange_once(s) and adjustments < 3:
            adjustments += 1
            time.sleep(10 * s.time_constant())  # type: ignore[union-attr]
