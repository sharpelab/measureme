from typing import TypedDict

# Sentinel value stored in measurement_config to identify sharpelab configs
SHARPELAB_SENTINEL = "__sharpelab__"


class ContactPair(TypedDict):
    channels: list[int]  # sr830 indices, e.g. [1, 2]
    contacts: list[str]  # wiring labels (parallel to channels), e.g. ["28-25", "25-24"]


class SharpeLabConfig(TypedDict):
    """Typed measurement_config written by sharpelab_nb.

    Stored in metadata['measurement_config']. Identifiable by the
    presence of the __sharpelab__ sentinel key.
    """

    __sharpelab__: bool
    channels: dict[str, str]  # sr830_N -> contact label (the original mc dict)
    contact_pairs: dict[str, ContactPair]  # role -> config


# Role name -> default LaTeX label
_ROLE_LABELS: dict[str, str] = {
    "curr": r"$I/I_0$",
    "long": r"$R_{xx}$ ($\Omega$)",
    "hall": r"$R_{yx}$ ($\Omega$)",
    "nl": r"$R_{NL}$ ($\Omega$)",
}


def label_for_role(role: str) -> str:
    """Derive a plot label from a contact pair role name.

    Matches the longest prefix: "long1", "long2" -> "long",
    "realhall", "fakehall" -> "hall", etc.
    """
    for prefix, label in sorted(_ROLE_LABELS.items(), key=lambda x: -len(x[0])):
        if prefix in role:
            return label
    return role
