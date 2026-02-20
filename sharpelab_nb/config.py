from typing import Any

from typing import Mapping

from sharpelab_nb.models import SHARPELAB_SENTINEL, ContactPair, SharpeLabConfig


def build_measurement_config(
    mc: dict[str, str],
    contact_pairs: dict[str, dict[str, Any]],
) -> SharpeLabConfig:
    """Merge a measurement config dict with contact pair definitions.

    Args:
        mc: Channel -> contact label mapping, e.g.
            {"sr830_1": "28-25", "sr830_2": "25-24", ...}
        contact_pairs: Role -> config mapping. Each value must have a
            "channels" key with a list of sr830 indices. e.g.
            {"long1": {"channels": [1, 2]}, "curr": {"channels": [4]}}

    Returns:
        A SharpeLabConfig dict suitable for passing as measurement_config
        to sweep.Station. Contains a sentinel for later identification.
    """
    pairs: dict[str, ContactPair] = {}
    for role, cp in contact_pairs.items():
        channels: list[int] = cp["channels"]
        contacts: list[str] = []
        for ch in channels:
            key = f"sr830_{ch}"
            if key not in mc:
                raise ValueError(f"Channel {key} (role {role!r}) not found in mc")
            contacts.append(mc[key])
        pairs[role] = ContactPair(channels=channels, contacts=contacts)

    return SharpeLabConfig(
        __sharpelab__=True,
        channels=mc,
        contact_pairs=pairs,
    )


def get_contact_pairs(
    measurement_config: Mapping[str, Any],
) -> dict[str, ContactPair] | None:
    """Extract contact pairs from a loaded measurement_config.

    Returns None if the config doesn't have the sharpelab sentinel.
    """
    if SHARPELAB_SENTINEL not in measurement_config:
        return None
    config: SharpeLabConfig = measurement_config  # type: ignore[assignment]
    return config["contact_pairs"]


def get_channels(
    measurement_config: Mapping[str, Any],
) -> dict[str, str] | None:
    """Extract the original mc channel dict from a loaded measurement_config.

    Returns None if the config doesn't have the sharpelab sentinel.
    """
    if SHARPELAB_SENTINEL not in measurement_config:
        return None
    config: SharpeLabConfig = measurement_config  # type: ignore[assignment]
    return config["channels"]
