"""Read temperatures from Lakeshore log files on the fridge PC.

The fridge control software (e.g. Lakeshore monitor) continuously
appends tab-delimited lines to log files.  Each line has the format::

    date\ttime\tvalue\tunit\tstatus\t...

We tail-read the last line and extract the temperature from the third-
to-last column (``content[-3]``).
"""

from __future__ import annotations

import os
import time

import qcodes


def _read_last_field(path: str, *, field_index: int = -3, retries: int = 5) -> float:
    """Tail-read a tab-delimited log file and return one float field.

    Parameters
    ----------
    path : str
        Absolute path to the log file (on the machine running Python).
    field_index : int
        Index into the tab-split columns of the last line.
    retries : int
        Number of attempts when the file is momentarily unreadable
        (e.g. being written to by another process).
    """
    content: list[str] = []
    remaining = retries
    while len(content) == 0 and remaining > 0:
        with open(path, "rb") as f:
            try:
                f.seek(-2, os.SEEK_END)
                while f.read(1) != b"\n":
                    f.seek(-2, os.SEEK_CUR)
                content = f.readline().decode().split("\t")
            except OSError:
                time.sleep(0.005)
                remaining -= 1
    if remaining == 0:
        raise TimeoutError(
            f"Failed to read temperature from {path} after {retries} retries"
        )
    return float(content[field_index])


def temperature_from_logfile(
    name: str,
    path: str,
    *,
    unit: str = "K",
    label: str | None = None,
) -> qcodes.Parameter:
    """Create a QCoDeS Parameter that reads temperature from a log file.

    Parameters
    ----------
    name : str
        QCoDeS parameter name (e.g. ``"T_probe"``).
    path : str
        Absolute path to the tab-delimited log file.
    unit : str
        Unit string for the parameter.
    label : str | None
        Human-readable label.  Defaults to *name*.
    """
    return qcodes.Parameter(
        name,
        unit=unit,
        label=label or name,
        get_cmd=lambda: _read_last_field(path),
    )
