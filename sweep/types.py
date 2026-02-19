from collections.abc import Sequence
from typing import Any, Callable, NamedTuple, TypedDict

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


class Metadata(TypedDict, total=False):
    # Common
    comments: list[Comment]
    type: str
    function: str
    columns: list[str]
    measurement_config: dict[str, str]
    interrupted: bool
    start_time: float
    end_time: float

    # measure only
    time: float

    # Timing
    delay: float
    max_duration: float | None
    slow_delay: float
    fast_delay: float

    # Parameter names (str for single-param, list[str] for multi-param)
    param: str | list[str]
    slow_param: str | list[str]
    fast_param: str | list[str]

    # Setpoints data (list[float] for single-param, list[list[float]] for multi-param)
    setpoints: list[float] | list[list[float]]
    slow_setpoints: list[float] | list[list[float]]
    fast_setpoints: list[float] | list[list[float]]
