from typing import Any

from qcodes.parameters import Parameter

# User comments attached to a sweep (strings or metadata dicts)
Comment = str | dict[str, Any]

# A QCoDeS parameter paired with its gain factor
ParamGain = tuple[Parameter, float]

__all__ = ["Comment", "Parameter", "ParamGain"]
