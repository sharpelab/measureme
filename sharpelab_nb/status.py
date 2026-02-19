from typing import Any

from qcodes.parameters import Parameter


class Status:
    """Reads a curated set of instrument parameters for quick status checks.

    Define once with your key parameters, then call repeatedly to get
    current values. Works as a debug tool and as a sweep comment source.

    Usage::

        status = Status(
            field=mag.field,
            T=temperature,
            V_tg=k_tg.volt,
            V_bg=k_bg.volt,
            I_ac=sr830_1.amplitude,
            f_ac=sr830_1.frequency,
        )

        status()                    # quick look at current state
        s.add_comment(status())     # attach snapshot to a sweep
    """

    def __init__(self, **params: Parameter) -> None:
        self._params = params

    def __call__(self) -> dict[str, Any]:
        return {name: p() for name, p in self._params.items()}

    def __repr__(self) -> str:
        return repr(self())
