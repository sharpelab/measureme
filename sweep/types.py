from collections.abc import Sequence
from typing import (
    Any,
    Callable,
    Final,
    Literal,
    NamedTuple,
    Protocol,
    TypedDict,
    runtime_checkable,
)

import numpy as np
from qcodes.parameters import Parameter

# Metadata schema version written by all sweep functions
METADATA_VERSION: Final = 2

# User comments attached to a sweep (strings or metadata dicts)
Comment = str | dict[str, Any]

# A QCoDeS parameter paired with its gain factor
ParamGain = tuple[Parameter, float]

# A sequence of numeric setpoints (list, range, np.ndarray, etc.)
Setpoints = Sequence[float] | np.ndarray


@runtime_checkable
class SnapReadable(Protocol):
    """Instrument supporting SNAP?-style coherent batch reads (e.g. SR830)."""

    SNAP_PARAMETERS: dict[str, str]

    def snap(self, *names: str) -> tuple[float, ...]: ...


@runtime_checkable
class BatchReadable(Protocol):
    """Instrument supporting get_values()-style batch reads (e.g. SR86x)."""

    PARAMETER_NAMES: dict[str, str]

    def get_values(self, *names: str) -> tuple[float, ...]: ...


class Hook(NamedTuple):
    """A hook callback with its bound positional arguments."""

    fn: Callable[..., Any]
    args: tuple[Any, ...]


# -- Metadata v2 schema (discriminated on "function") --


class _BaseMetadata(TypedDict):
    version: int
    comments: list[Comment]
    columns: list[str]
    measurement_config: dict[str, Any]
    instruments: dict[str, Any]
    interrupted: bool
    start_time: float
    end_time: float


class MeasureMetadata(_BaseMetadata):
    function: Literal["measure"]
    type: Literal["0D"]


class WatchMetadata(_BaseMetadata):
    function: Literal["watch"]
    type: Literal["1D"]
    delay: float
    max_duration: float | None


class SweepMetadata(_BaseMetadata):
    function: Literal["sweep"]
    type: Literal["1D"]
    delay: float
    param: str
    setpoints: list[float]


class MultisweepMetadata(_BaseMetadata):
    function: Literal["multisweep"]
    type: Literal["1D"]
    delay: float
    params: list[str]
    setpoints: list[list[float]]


class MegasweepMetadata(_BaseMetadata):
    function: Literal["megasweep"]
    type: Literal["2D"]
    slow_delay: float
    fast_delay: float
    slow_param: str
    fast_param: str
    slow_setpoints: list[float]
    fast_setpoints: list[float]


class MultimegasweepMetadata(_BaseMetadata):
    function: Literal["multimegasweep"]
    type: Literal["2D"]
    slow_delay: float
    fast_delay: float
    slow_params: list[str]
    fast_params: list[str]
    slow_setpoints: list[list[float]]
    fast_setpoints: list[list[float]]


Metadata = (
    MeasureMetadata
    | WatchMetadata
    | SweepMetadata
    | MultisweepMetadata
    | MegasweepMetadata
    | MultimegasweepMetadata
)
