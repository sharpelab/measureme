"""Progress bar that survives Jupyter browser disconnects.

Unlike ``tqdm.notebook`` (which relies on ipywidgets comm channels),
this renders progress as HTML and updates it via IPython's display
protocol (IOPub).  When a browser tab is closed and reopened, the
kernel's next ``update_display`` message travels over the fresh
IOPub connection and the bar resumes updating.

Falls back to ``tqdm.std`` when IPython is not available (CLI usage).
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Iterable, Iterator


def _in_jupyter() -> bool:
    """Check if we're running inside a Jupyter notebook kernel."""
    try:
        ip = get_ipython()  # type: ignore[name-defined]  # noqa: F821
        return ip.__class__.__name__ == "ZMQInteractiveShell"
    except NameError:
        return False


def _format_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


class progress:
    """Drop-in replacement for ``tqdm`` that uses HTML display in Jupyter.

    Usage is identical to tqdm::

        for item in progress(items):
            ...

    For nested loops (e.g. megasweep), use ``position`` and ``leave``::

        for outer in progress(slow_v, position=0):
            for inner in progress(fast_v, position=1, leave=False):
                ...
    """

    # Throttle display updates to avoid flooding IOPub.
    _MIN_INTERVAL: float = 0.1  # seconds

    def __init__(
        self,
        iterable: Iterable[Any] | None = None,
        total: int | None = None,
        position: int | None = None,
        leave: bool = True,
        **kwargs: Any,
    ) -> None:
        self._iterable = iterable
        self._total = total
        if (
            self._total is None
            and iterable is not None
            and hasattr(iterable, "__len__")
        ):
            self._total = len(iterable)  # type: ignore[arg-type]
        self._position = position
        self._leave = leave
        self.n: int = 0
        self._start: float = time.monotonic()
        self._last_display: float = 0.0
        self._display_id: str = f"sweep-progress-{uuid.uuid4().hex[:8]}"
        self._displayed: bool = False
        self._closed: bool = False

    def _render_html(self) -> str:
        elapsed = time.monotonic() - self._start
        pct = (self.n / self._total * 100) if self._total else 0
        rate = self.n / elapsed if elapsed > 0 else 0
        remaining = (self._total - self.n) / rate if rate > 0 and self._total else 0

        elapsed_str = _format_time(elapsed)
        remaining_str = _format_time(remaining)
        rate_str = f"{rate:.2f}it/s" if rate < 100 else f"{rate:.0f}it/s"

        if self._closed:
            bar_color = "#4caf50" if self.n >= (self._total or 0) else "#f44336"
        else:
            bar_color = "#1976d2"

        count = f"{self.n}/{self._total}" if self._total else f"{self.n}"

        return (
            '<div style="display:flex;align-items:center;gap:8px;'
            'font-family:monospace;font-size:12px;margin:2px 0;">'
            f'<span style="min-width:35px;text-align:right">{pct:.0f}%</span>'
            '<div style="flex:1;max-width:300px;height:18px;'
            'background:#e0e0e0;border-radius:3px;overflow:hidden;">'
            f'<div style="width:{min(pct, 100):.1f}%;height:100%;'
            f"background:{bar_color};"
            'transition:width 0.2s;"></div></div>'
            f"<span>{count} [{elapsed_str}&lt;{remaining_str}, {rate_str}]</span>"
            "</div>"
        )

    def _display(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and (now - self._last_display) < self._MIN_INTERVAL:
            return
        self._last_display = now

        from IPython.display import HTML, display, update_display

        html = HTML(self._render_html())
        if not self._displayed:
            display(html, display_id=self._display_id)
            self._displayed = True
        else:
            update_display(html, display_id=self._display_id)

    def update(self, n: int = 1) -> None:
        self.n += n
        self._display()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if not self._leave and self._displayed:
            from IPython.display import HTML, update_display

            update_display(HTML(""), display_id=self._display_id)
        else:
            self._display(force=True)

    def __iter__(self) -> Iterator[Any]:
        self._display(force=True)
        try:
            for item in self._iterable:  # type: ignore[union-attr]
                yield item
                self.update()
        except BaseException:
            self.close()
            raise
        self.close()

    def __enter__(self) -> progress:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


def tqdm(iterable: Iterable[Any] | None = None, **kwargs: Any) -> progress | Any:
    """Smart constructor: HTML progress in Jupyter, text tqdm otherwise."""
    if _in_jupyter():
        return progress(iterable, **kwargs)
    from tqdm.std import tqdm as std_tqdm

    return std_tqdm(iterable, **kwargs)
