"""Lab-specific constants for Sharpe Lab measurement setups."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FridgeConfig:
    """Constants for a specific fridge/cryostat setup."""

    name: str
    coil_constant: float  # T/A
    temp_logfiles: dict[str, str] = field(default_factory=dict)


TOPLOADER = FridgeConfig(
    name="toploader",
    coil_constant=0.116783,
    temp_logfiles={
        "T_probe": r"C:\Users\toploader\temperature_logs\Probe1_MixingCh_low.txt",
        "T_fridge": r"C:\Users\toploader\temperature_logs\Fridge_MixingCh_low.txt",
        "T_magnet": r"C:\Users\toploader\temperature_logs\Fridge_Magnet.txt",
    },
)
