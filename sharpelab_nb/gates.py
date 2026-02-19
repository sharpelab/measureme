from typing import Any


def calculate_gate_voltages(
    n: Any,
    D: Any,
    dtg: float = 16,
    dbg: float = 25.5,
    ep: float = 3,
) -> tuple[Any, Any]:
    """Convert carrier density and displacement field to gate voltages.

    Args:
        n: Carrier density (cm^-2).
        D: Displacement field (V/nm).
        dtg: Top gate dielectric thickness (nm).
        dbg: Back gate dielectric thickness (nm).
        ep: Dielectric constant of hBN.

    Returns:
        (Vtg, Vbg) gate voltages.
    """
    conversion_factor = 5.52634936
    Vtg = (n / (ep * conversion_factor) + 2 * D / ep) * dtg / 2
    Vbg = dbg * (n / (ep * conversion_factor) - Vtg / dtg)
    return Vtg, Vbg


def calculate_n_D(
    Vtg: Any,
    Vbg: Any,
    dtg: float = 16,
    dbg: float = 25.5,
    ep: float = 3,
) -> tuple[Any, Any]:
    """Convert gate voltages to carrier density and displacement field.

    Args:
        Vtg: Top gate voltage (V).
        Vbg: Back gate voltage (V).
        dtg: Top gate dielectric thickness (nm).
        dbg: Back gate dielectric thickness (nm).
        ep: Dielectric constant of hBN.

    Returns:
        (n, D) where n is carrier density (cm^-2) and D is displacement field (V/nm).
    """
    conversion_factor = 5.52634936
    n = (Vbg / dbg + Vtg / dtg) * ep * conversion_factor
    D = 0.5 * ep * (Vtg / dtg - Vbg / dbg)
    return n, D


def comment_to_gates(comment: str, delim: str = ":") -> tuple[float, float]:
    """Parse a comment string to extract gate voltages.

    Expects format like ``"label: (Vtg, Vbg)"``.

    Returns:
        (Vtg, Vbg) as floats.
    """
    parts = comment.split(delim)
    values_part = parts[-1].strip()
    values = values_part.strip("()").split(",")
    Vtg = float(values[0].strip())
    Vbg = float(values[1].strip())
    return Vtg, Vbg
