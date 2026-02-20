from __future__ import annotations

from typing import Any

import matplotlib.pyplot as plt
import matplotlib.figure
import matplotlib.axes
import matplotlib.collections
import numpy as np

import sweep.sweep_load as sl
from sharpelab_nb.config import get_contact_pairs
from sharpelab_nb.gates import calculate_n_D
from sharpelab_nb.models import ContactPair, label_for_role


class SweepPlotResult:
    """Result of plot_sweep. Holds figures/axes for post-hoc adjustments.

    Access axes by role and channel index::

        result = plot_sweep(file_path, [1541, 1542])
        result.ax("long1", 1).axhline(100, color='red')
        result.ax("long1", 1).set_title("custom title")

    Or iterate all panels::

        for key, (fig, ax_val, ax_phase) in result.panels.items():
            ax_val.set_xlim(0, 10)
    """

    def __init__(self) -> None:
        # (role, channel_index) -> (fig, value_axes, phase_axes)
        self.panels: dict[
            tuple[str, int],
            tuple[matplotlib.figure.Figure, matplotlib.axes.Axes, matplotlib.axes.Axes],
        ] = {}

    def ax(self, role: str, channel: int) -> matplotlib.axes.Axes:
        """Get the value (left) axes for a given role and channel."""
        return self.panels[(role, channel)][1]

    def phase_ax(self, role: str, channel: int) -> matplotlib.axes.Axes:
        """Get the phase (right) axes for a given role and channel."""
        return self.panels[(role, channel)][2]

    def fig(self, role: str, channel: int) -> matplotlib.figure.Figure:
        """Get the figure for a given role and channel."""
        return self.panels[(role, channel)][0]


def _extract_contact_pairs(file_path: str, files: list[int]) -> dict[str, ContactPair]:
    """Extract contact pairs from the first file's metadata."""
    meta = sl.load_meta(file_path, files[0])
    mc = meta.get("measurement_config")
    if mc is None:
        raise ValueError(f"File {files[0]} has no measurement_config in metadata")
    cp = get_contact_pairs(mc)
    if cp is None:
        raise ValueError(
            f"File {files[0]} measurement_config has no sharpelab sentinel. "
            "Pass contact_pairs= explicitly or backfill metadata."
        )
    return cp


def _find_current_column(
    contact_pairs: dict[str, ContactPair],
) -> str:
    """Find the sr830 column name for the current measurement."""
    if "curr" not in contact_pairs:
        raise ValueError(
            "contact_pairs must have a 'curr' role to identify current channel"
        )
    curr_channels = contact_pairs["curr"]["channels"]
    if len(curr_channels) != 1:
        raise ValueError(f"Expected exactly 1 current channel, got {curr_channels}")
    return f"sr830_{curr_channels[0]}_X"


def _get_xs(data: dict[str, Any]) -> Any:
    """Extract x-axis values from loaded data."""
    xs = data.get("xs")
    if xs is not None:
        xs = np.asarray(xs)
        if xs.ndim > 1:
            xs = xs[0]
        return xs
    return None


def _label_for_param(param: str | None) -> str:
    """Derive an x-axis label from the sweep parameter name."""
    if param is None:
        return ""
    p = param.lower()
    if "field" in p or "mag" in p:
        return r"$B$ (T)"
    if "tg" in p:
        return r"$V_{tg}$ (V)"
    if "bg" in p:
        return r"$V_{bg}$ (V)"
    if "si" in p:
        return r"$V_{si}$ (V)"
    return param


def plot_sweep(
    file_path: str,
    files: list[int],
    contact_pairs: dict[str, ContactPair] | None = None,
    *,
    log: bool = False,
    current_mask: float = 0.0,
    figsize: tuple[float, float] = (16.18, 5),
) -> SweepPlotResult:
    """Plot 1D sweep data for each contact pair channel.

    Creates a two-panel figure (value + phase) per channel, with all
    files overlaid as separate traces. Contact pairs are auto-extracted
    from metadata if not provided.

    The ``curr`` role is plotted as raw current (I), all other roles
    as resistance (R = V/I). Files are colored using the inferno colormap.

    Args:
        file_path: Base directory containing measurement data.
        files: List of run IDs to overlay.
        contact_pairs: Role -> ContactPair mapping. If None, extracted
            from the first file's metadata (requires sharpelab sentinel).
        log: If True, use semilogy for the value panel.
        current_mask: Mask out points where |I| < current_mask * max(|I|).
            Set to 0.0 (default) to disable masking.
        figsize: Figure size (width, height).

    Returns:
        SweepPlotResult with axes accessible for further customization.
    """
    if contact_pairs is None:
        contact_pairs = _extract_contact_pairs(file_path, files)

    current_col = _find_current_column(contact_pairs)
    result = SweepPlotResult()

    # Read sweep param from first file for axis labels
    meta = sl.load_meta(file_path, files[0])
    sweep_param: str | None = meta.get("param")
    x_label = _label_for_param(sweep_param)

    for role, cp in contact_pairs.items():
        channels = cp["channels"]
        contacts = cp["contacts"]
        is_curr = role == "curr"
        label = label_for_role(role)

        for i, ch in enumerate(channels):
            fig, (ax_val, ax_phase) = plt.subplots(1, 2, figsize=figsize)
            ax_val.set_facecolor("lightgrey")

            col_x = f"sr830_{ch}_X"
            col_p = f"sr830_{ch}_P"
            contact_label = contacts[i] if i < len(contacts) else ""

            for file_id in files:
                data = sl.pload(file_path, file_id)

                current = data[current_col]

                if is_curr:
                    y = current
                else:
                    Vxx = data[col_x]
                    y = Vxx / current
                    if current_mask > 0:
                        mask = np.abs(current) < current_mask * np.nanmax(
                            np.abs(current)
                        )
                        y = np.ma.array(y, mask=mask)

                xs = _get_xs(data)
                x = xs[: len(y)] if xs is not None else np.arange(len(y))

                phase = data.get(col_p)

                plot_fn = ax_val.semilogy if log else ax_val.plot
                plot_fn(x, y, label=f"#{file_id}")

                if phase is not None:
                    ax_phase.plot(x[: len(phase)], phase, label=f"#{file_id}")

            ax_val.set_ylabel(label)
            ax_val.set_xlabel(x_label)
            ax_val.set_title(f"{role} ch{ch} ({contact_label})")
            ax_val.legend()

            ax_phase.set_ylabel("Phase (deg)")
            ax_phase.set_xlabel(x_label)
            ax_phase.set_title(f"{role} ch{ch} phase")
            ax_phase.legend()

            result.panels[(role, ch)] = (fig, ax_val, ax_phase)

    return result


class GatemapPlotResult:
    """Result of plot_gatemap. Holds figures/axes/meshes for post-hoc adjustments.

    Access by role and channel index::

        result = plot_gatemap(file_path, 1265, contact_pairs=cp)
        result.mesh("long1", 1).set_cmap("RdBu_r")
        result.ax("long1", 1).set_title("custom title")

    Or iterate all panels::

        for key, (fig, ax, mesh) in result.panels.items():
            ax.set_xlim(-5, 5)
    """

    def __init__(self) -> None:
        # (role, channel_index) -> (fig, axes, quadmesh)
        self.panels: dict[
            tuple[str, int],
            tuple[
                matplotlib.figure.Figure,
                matplotlib.axes.Axes,
                matplotlib.collections.QuadMesh,
            ],
        ] = {}

    def ax(self, role: str, channel: int) -> matplotlib.axes.Axes:
        """Get the axes for a given role and channel."""
        return self.panels[(role, channel)][1]

    def fig(self, role: str, channel: int) -> matplotlib.figure.Figure:
        """Get the figure for a given role and channel."""
        return self.panels[(role, channel)][0]

    def mesh(self, role: str, channel: int) -> matplotlib.collections.QuadMesh:
        """Get the QuadMesh for colormap/norm adjustments."""
        return self.panels[(role, channel)][2]


def plot_gatemap(
    file_path: str,
    file: int,
    contact_pairs: dict[str, ContactPair] | None = None,
    *,
    nD: bool = False,
    dtg: float = 16,
    dbg: float = 25.5,
    ep: float = 3,
    current_mask: float = 0.0,
    figsize: tuple[float, float] = (10, 8),
) -> GatemapPlotResult:
    """Plot 2D raster gatemap data as colormesh per contact pair channel.

    Creates one figure per channel with a pcolormesh colormap. Contact pairs
    are auto-extracted from metadata if not provided.

    The ``curr`` role is plotted as raw current (I), all other roles
    as resistance (R = V/I).

    Args:
        file_path: Base directory containing measurement data.
        file: Run ID of the 2D megasweep.
        contact_pairs: Role -> ContactPair mapping. If None, extracted
            from the file's metadata (requires sharpelab sentinel).
        nD: If True, convert gate voltages to carrier density (n) and
            displacement field (D). Requires slow/fast params to contain
            "tg" and "bg".
        dtg: Top gate dielectric thickness (nm), for n/D conversion.
        dbg: Back gate dielectric thickness (nm), for n/D conversion.
        ep: Dielectric constant of hBN, for n/D conversion.
        current_mask: Mask out points where |I| < current_mask * max(|I|).
            Set to 0.0 (default) to disable masking.
        figsize: Figure size (width, height).

    Returns:
        GatemapPlotResult with axes/meshes accessible for further customization.
    """
    if contact_pairs is None:
        contact_pairs = _extract_contact_pairs(file_path, [file])

    current_col = _find_current_column(contact_pairs)
    data = sl.pload(file_path, file)
    meta = sl.load_meta(file_path, file)

    # xs = fast setpoints, ys = slow setpoints
    xs = np.asarray(data["xs"])
    ys = np.asarray(data["ys"])
    fast_param: str | None = meta.get("fast_param")
    slow_param: str | None = meta.get("slow_param")

    if nD:
        # Identify which axis is tg and which is bg
        fast_is_tg = fast_param is not None and "tg" in fast_param.lower()
        fast_is_bg = fast_param is not None and "bg" in fast_param.lower()
        slow_is_tg = slow_param is not None and "tg" in slow_param.lower()
        slow_is_bg = slow_param is not None and "bg" in slow_param.lower()

        if not ((fast_is_tg and slow_is_bg) or (fast_is_bg and slow_is_tg)):
            raise ValueError(
                f"nD=True requires one tg and one bg axis, got "
                f"fast_param={fast_param!r}, slow_param={slow_param!r}"
            )

        # Build 2D grids from 1D setpoints
        fast_grid, slow_grid = np.meshgrid(xs, ys)

        if fast_is_tg:
            Vtg_grid, Vbg_grid = fast_grid, slow_grid
        else:
            Vtg_grid, Vbg_grid = slow_grid, fast_grid

        n_grid, D_grid = calculate_n_D(Vtg_grid, Vbg_grid, dtg, dbg, ep)
        # Convention: n on x-axis, D on y-axis
        x_plot = n_grid
        y_plot = D_grid
        x_label = r"$n$ ($10^{12}$ cm$^{-2}$)"
        y_label = r"$D/\epsilon_0$ (V/nm)"
    else:
        x_plot = xs
        y_plot = ys
        x_label = _label_for_param(fast_param)
        y_label = _label_for_param(slow_param)

    current = data[current_col]
    result = GatemapPlotResult()

    for role, cp in contact_pairs.items():
        channels = cp["channels"]
        contacts = cp["contacts"]
        is_curr = role == "curr"
        colorbar_label = label_for_role(role)

        for i, ch in enumerate(channels):
            col_x = f"sr830_{ch}_X"
            contact_label = contacts[i] if i < len(contacts) else ""

            if is_curr:
                z = current
            else:
                Vxx = data[col_x]
                z = Vxx / current
                if current_mask > 0:
                    mask = np.abs(current) < current_mask * np.nanmax(np.abs(current))
                    z = np.ma.array(z, mask=mask)

            fig, ax = plt.subplots(figsize=figsize)
            mesh = ax.pcolormesh(x_plot, y_plot, z, shading="auto")
            fig.colorbar(mesh, ax=ax, label=colorbar_label)

            ax.set_xlabel(x_label)
            ax.set_ylabel(y_label)
            ax.set_title(f"{role} ch{ch} ({contact_label})")

            result.panels[(role, ch)] = (fig, ax, mesh)

    return result
