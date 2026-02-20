"""Lab-specific constants for Sharpe Lab measurement setups."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FridgeConfig:
    """Constants for a specific fridge/cryostat setup."""

    name: str
    coil_constant: float  # T/A


TOPLOADER = FridgeConfig(
    name="toploader",
    coil_constant=0.116783,
)
