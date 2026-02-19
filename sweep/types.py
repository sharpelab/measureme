from collections.abc import Sequence
from typing import Any, Callable, NamedTuple

import numpy as np
from qcodes.parameters import Parameter

# User comments attached to a sweep (strings or metadata dicts)
Comment = str | dict[str, Any]

# A QCoDeS parameter paired with its gain factor
ParamGain = tuple[Parameter, float]

# A sequence of numeric setpoints (list, range, np.ndarray, etc.)
Setpoints = Sequence[float] | np.ndarray


class Hook(NamedTuple):
    """A hook callback with its bound positional arguments."""

    fn: Callable[..., Any]
    args: tuple[Any, ...]
