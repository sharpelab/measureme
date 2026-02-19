from collections.abc import Sequence
from typing import Any, Callable, Literal, NamedTuple, TypedDict, cast

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


# -- Metadata v2 schema (discriminated on "function") --


class _BaseMetadata(TypedDict):
    version: int
    comments: list[Comment]
    columns: list[str]
    measurement_config: dict[str, str]
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


def migrate_metadata(raw: dict[str, Any]) -> Metadata:
    """Migrate v1 metadata to v2. V2 passes through unchanged."""
    if raw.get("version", 0) >= 2:
        return cast(Metadata, raw)

    raw["version"] = 2
    fn = raw.get("function")

    if fn == "measure":
        t = raw.pop("time", 0.0)
        raw.setdefault("start_time", t)
        raw.setdefault("end_time", t)
        raw.setdefault("interrupted", False)
    elif fn == "multisweep":
        if "param" in raw:
            raw["params"] = raw.pop("param")
    elif fn == "multimegasweep":
        if "slow_param" in raw:
            raw["slow_params"] = raw.pop("slow_param")
        if "fast_param" in raw:
            raw["fast_params"] = raw.pop("fast_param")

    return cast(Metadata, raw)
