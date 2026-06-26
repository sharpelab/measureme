import contextlib
import dataclasses
import functools
import os
import sys
import signal
import time
import concurrent.futures
import inspect
from collections import defaultdict
from collections.abc import Iterator
from typing import Any, Callable

from sweep.progress import interruptible_sleep, tqdm
import logging

from IPython import display

import sweep.db
import sweep.plot
from qcodes.instrument import InstrumentBase

from typing import cast

from sweep.types import (
    METADATA_VERSION,
    BatchReadable,
    Comment,
    Hook,
    MegasweepMetadata,
    Metadata,
    MultimegasweepMetadata,
    MultisweepMetadata,
    Parameter,
    ParamGain,
    Setpoints,
    SnapReadable,
    SweepMetadata,
    WatchMetadata,
)

import numpy as np

# TODO
# down sampling measurement

BASEDIR: str | None = None

_shutdown_handler: Callable[[], None] | None = None
_shutdown_requested: bool = False
_sweep_active: bool = False


def set_basedir(path: str) -> None:
    global BASEDIR
    BASEDIR = path


def set_shutdown_handler(fn: Callable[[], None]) -> None:
    """Register a function to call on graceful shutdown (e.g. ramp down instruments)."""
    global _shutdown_handler
    _shutdown_handler = fn


def request_shutdown() -> None:
    """Trigger graceful shutdown. Thread-safe — call from UPS monitor or timer."""
    global _shutdown_requested
    _shutdown_requested = True
    if not _sweep_active and _shutdown_handler is not None:
        _shutdown_handler()


def shutdown_requested() -> bool:
    """True once request_shutdown() has fired (UPS/timer graceful shutdown)."""
    return _shutdown_requested


def _sec_to_str(d: float) -> str:
    h, m, s = int(d / 3600), int(d / 60) % 60, int(d) % 60
    return f"{h}h {m}m {s}s"


def list_measurements(basedir: str | None = None) -> None:
    global BASEDIR
    if basedir is not None:
        path = basedir
    elif BASEDIR is not None:
        path = BASEDIR
    else:
        path = os.getcwd()

    def line(i: int, md: Metadata) -> str:
        data = [str(i)]
        data.append(
            time.strftime("%Y-%b-%d %H:%M:%S", time.localtime(md["start_time"]))
        )
        data.append(_sec_to_str(md["end_time"] - md["start_time"]))
        data.append(md["type"])
        data.append("yes" if md["interrupted"] else "")
        fn = md["function"]
        if fn == "sweep":
            data.append(cast(SweepMetadata, md)["param"])
        elif fn == "multisweep":
            data.append(", ".join(cast(MultisweepMetadata, md)["params"]))
        else:
            data.append("")
        if fn == "megasweep":
            m = cast(MegasweepMetadata, md)
            data.append(m["slow_param"])
            data.append(m["fast_param"])
        elif fn == "multimegasweep":
            m = cast(MultimegasweepMetadata, md)
            data.append(", ".join(m["slow_params"]))
            data.append(", ".join(m["fast_params"]))
        else:
            data.append("")
            data.append("")
        return "|" + "|".join(data) + "|"

    data = [
        "|ID|Start time|Duration|Type|Interrupted|Param|Slow param|Fast param|",
        "|---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|",
    ]
    i = 0
    while True:
        try:
            with sweep.db.Reader(path, i) as r:
                data.append(line(i, r.metadata))
            i += 1
        except Exception:
            break
    display.display_markdown("\n".join(data), raw=True)


def measurement_info(i: int, basedir: str | None = None) -> None:
    global BASEDIR
    if basedir is not None:
        path = basedir
    elif BASEDIR is not None:
        path = BASEDIR
    else:
        path = os.getcwd()

    def format_list(lst: list[Any]) -> str:
        newls: list[Any] = []
        if len(lst) > 10:
            newls = lst[:3] + ["..."] + lst[-3:]
        else:
            newls = lst
        return "[" + ", ".join([str(x) for x in newls]) + "]"

    with sweep.db.Reader(path, i) as r:
        print("ID:", i)
        print("Data path:", r.datapath)
        md = r.metadata
        print("Comments:", md["comments"])
        print(
            "Start time:",
            time.strftime("%Y-%b-%d %H:%M:%S", time.localtime(md["start_time"])),
        )
        print("Duration:", _sec_to_str(md["end_time"] - md["start_time"]))
        print("Type:", md["type"])
        print("Interrupted:", "yes" if md["interrupted"] else "no")
        fn = md["function"]
        if fn == "sweep":
            m = cast(SweepMetadata, md)
            print("Param:", m["param"])
            print("Delay:", m["delay"])
            print("Setpoints:", format_list(m["setpoints"]))
        elif fn == "multisweep":
            m = cast(MultisweepMetadata, md)
            print("Params:", m["params"])
            print("Delay:", m["delay"])
            print("Setpoints:", format_list(m["setpoints"]))
        elif fn == "megasweep":
            m = cast(MegasweepMetadata, md)
            print("Slow param:", m["slow_param"])
            print("Fast param:", m["fast_param"])
            print("Slow delay:", m["slow_delay"])
            print("Fast delay:", m["fast_delay"])
            print("Slow setpoints:", format_list(m["slow_setpoints"]))
            print("Fast setpoints:", format_list(m["fast_setpoints"]))
        elif fn == "multimegasweep":
            m = cast(MultimegasweepMetadata, md)
            print("Slow params:", m["slow_params"])
            print("Fast params:", m["fast_params"])
            print("Slow delay:", m["slow_delay"])
            print("Fast delay:", m["fast_delay"])
            print("Slow setpoints:", format_list(m["slow_setpoints"]))
            print("Fast setpoints:", format_list(m["fast_setpoints"]))
        elif fn == "watch":
            print("Delay:", cast(WatchMetadata, md)["delay"])
        print("Columns:", ", ".join(md["columns"]))


@dataclasses.dataclass(repr=False)
class SweepResult:
    basedir: str
    id: int
    metadata: Metadata
    datapath: str


def _interruptible(func: Callable[..., Any]) -> Callable[..., Any]:
    # We don't want to allow interrupts while communicating with
    # instruments. This checks for interrupts after measuring.
    # TODO: Allow potentially the param(setpoint) if possible.
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        global _sweep_active, _shutdown_requested
        args[0].interrupt_requested = False
        _sweep_active = True

        def handler(signum: int, frame: Any) -> None:
            args[0].interrupt_requested = True

        old_handler = signal.signal(signal.SIGINT, handler)
        try:
            result = func(*args, **kwargs)
        finally:
            signal.signal(signal.SIGINT, old_handler)
            _sweep_active = False

        if _shutdown_requested and _shutdown_handler is not None:
            _shutdown_handler()
            _shutdown_requested = False

        return result

    return wrapper


class Station:
    """A Station is a collection of parameters that can be measured.

    You can do 0D (measure), 1D (sweep), and 2D (megasweep) sweeps, and you can
    measure over time with watch.
    """

    def __init__(
        self,
        measurement_config: dict[str, str] | None = None,
        basedir: str | None = None,
        verbose: bool = True,
    ) -> None:
        """Create a Station.
        measurement_config: dict mapping hardware to measurements
        """
        global BASEDIR
        if basedir is not None:
            self._basedir: str = basedir
        elif BASEDIR is not None:
            self._basedir = BASEDIR
        else:
            self._basedir = os.getcwd()

        self._verbose: bool = verbose
        self._init_logger()
        self._params: list[ParamGain] = []
        self._measurement_config: dict[str, str] = measurement_config or {}
        self._plotter = sweep.plot.Plotter()
        self._run_befores: list[Hook] = []
        self._run_afters: list[Hook] = []
        self._comments: list[Comment] = []
        self._interrupted: bool = False
        self.interrupt_requested: bool = False
        self.logger.debug("Station initialized")

    def _init_logger(self) -> None:
        self.logger = logging.getLogger("sweep_log" + str(np.random.randint(2**31)))
        file_handler = logging.FileHandler(
            filename=os.path.join(self._basedir, "log.log")
        )
        file_handler.setLevel(logging.DEBUG)

        stream_handler = logging.StreamHandler(sys.stdout)
        if self._verbose:
            stream_handler.setLevel(logging.INFO)
        else:
            stream_handler.setLevel(logging.WARNING)

        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        file_handler.setFormatter(formatter)
        stream_handler.setFormatter(formatter)

        self.logger.addHandler(file_handler)
        self.logger.addHandler(stream_handler)
        self.logger.setLevel(logging.DEBUG)

    def add_comment(self, comment: Comment) -> None:
        self._comments.append(comment)

    def log_comment(self, comment: str) -> None:
        self.logger.info(f"Comment: {comment}")

    def register_run_before(
        self, fn: Callable[..., Any], args: tuple[Any, ...]
    ) -> None:
        """
        Register a function to run before/after (see below) each measurement step.

        Parameters
        ----------
        fn : callable
            Function called as: fn(*args, **context)
        args : tuple
            Positional arguments passed to fn (must be a tuple).

        Context
        -------
        The following context arguments may be provided to hooks:

        station : Station
            The active Station instance.
        writer : sweep.db.Writer
            The current data writer (available inside measurement loops).
        data : list
            The most recent measured data point (run-after only).

        Hooks receive only the context arguments they explicitly accept.
        Hooks without contexts can be safely run

        Example
        -------
        >>> def before(msg, writer=None):
        ...     print(msg, writer.id)
        >>> station.register_run_before(before, args=("hello",))
        """

        if not isinstance(args, tuple):
            raise TypeError("args must be a tuple, e.g. (value,)")
        self._run_befores.append(Hook(fn, args))

    def _run_run_befores(self, **context: Any) -> None:
        for fn, args in self._run_befores:
            sig = inspect.signature(fn)

            accepted = {k: v for k, v in context.items() if k in sig.parameters}

            fn(*args, **accepted)

    def register_run_after(self, fn: Callable[..., Any], args: tuple[Any, ...]) -> None:
        if not isinstance(args, tuple):
            raise TypeError("args must be a tuple, e.g. (value,)")
        self._run_afters.append(Hook(fn, args))

    def _run_run_afters(self, **context: Any) -> None:
        for fn, args in self._run_afters:
            sig = inspect.signature(fn)

            accepted = {k: v for k, v in context.items() if k in sig.parameters}

            fn(*args, **accepted)

    def _sweep_context(self) -> contextlib.AbstractContextManager[None]:
        return contextlib.nullcontext()

    def _init_metadata(
        self, w: sweep.db.Writer, *, columns: list[str], **extra: Any
    ) -> None:
        w.metadata["version"] = METADATA_VERSION
        w.metadata["comments"] = self._comments
        w.metadata["columns"] = columns
        w.metadata["measurement_config"] = self._measurement_config
        w.metadata["instruments"] = self._instruments()
        w.metadata["interrupted"] = False
        w.metadata["start_time"] = time.time()
        w.metadata.update(extra)
        w.update_metadata()

    def _measure(self) -> list[float]:
        return [p() / gain for p, gain in self._params]

    def _col_names(self) -> list[str]:
        return [p.full_name for p, _ in self._params]

    def _instruments(self) -> dict[str, Any]:
        instruments: dict[str, Any] = {}
        for p, gain in self._params:
            inst = p.instrument
            if inst is None:
                continue
            name = inst.name
            if name not in instruments:
                instruments[name] = {
                    "snapshot": inst.snapshot(),
                    "parameters": {},
                }
            instruments[name]["parameters"][p.full_name] = {"gain": gain}
        return instruments

    def follow_param(self, param: Parameter, gain: float = 1.0) -> "Station":
        self._params.append((param, gain))
        self.logger.debug(f"Follow paramter: {param.full_name}, gain: {gain}")
        return self

    fp = follow_param

    def plot(self, x: Any, y: Any, z: Any = None) -> None:
        self._plotter.plot(x, y, z)

    def reset_plots(self) -> None:
        self._plotter.reset_plots()

    def reset(self) -> None:
        self._interrupted = False
        self.logger.debug("Reseting station")

    def _check_interrupted(self) -> None:
        if self._interrupted:
            raise InterruptedError(
                "Station was previously interrupted, either remake it or use station.reset()"
            )

    def _should_stop(self) -> bool:
        return self.interrupt_requested or _shutdown_requested

    def ramp(self, param: Parameter, setpoint: float) -> None:
        cur_value = param()
        self.logger.info(f"Ramping {param.full_name}: {cur_value} -> {setpoint}")
        param(setpoint)

    def read(self, param: Parameter, gain: float = 1.0) -> None:
        val = param() / gain
        self.logger.info(f"Reading {param.full_name}: {val}")

    def read_all(self) -> None:
        self.logger.info("Reading all parameters:")
        [self.read(p, gain=gain) for p, gain in self._params]

    def measure(self) -> SweepResult:
        self._check_interrupted()
        with self._sweep_context(), sweep.db.Writer(self._basedir) as w:
            self.logger.info(f"Starting measure with ID {w.id}")
            self._init_metadata(
                w,
                type="0D",
                function="measure",
                columns=["time"] + self._col_names(),
            )

            self._run_run_befores(
                station=self,
                writer=w,
            )

            data = [time.time()] + self._measure()
            w.add_point(data)

            self._run_run_afters(
                station=self,
                data=data,
                writer=w,
            )

            w.metadata["end_time"] = time.time()

        self.logger.info(f"Data saved in {w.datapath}")
        return SweepResult(self._basedir, w.id, cast(Metadata, w.metadata), w.datapath)

    @_interruptible
    def watch(
        self, delay: float = 0.0, max_duration: float | None = None
    ) -> SweepResult:
        self._check_interrupted()
        with (
            self._sweep_context(),
            sweep.db.Writer(self._basedir) as w,
            self._plotter as p,
        ):
            self.logger.info(f"Starting watch with ID {w.id}")
            self._init_metadata(
                w,
                type="1D",
                function="watch",
                delay=delay,
                max_duration=max_duration,
                columns=["time"] + self._col_names(),
            )
            p.set_cols(w.metadata["columns"])

            t_start = time.monotonic()  # Can't go backwards!
            while max_duration is None or time.monotonic() - t_start < max_duration:
                time.sleep(delay)

                self._run_run_befores(
                    station=self,
                    writer=w,
                )

                data = [time.time()] + self._measure()
                w.add_point(data)
                p.add_point(data)

                self._run_run_afters(
                    station=self,
                    data=data,
                    writer=w,
                )

                if self._should_stop():
                    self.logger.warning(f"ID {w.id} INTERRUPTED")
                    self._interrupted = True
                    w.metadata["interrupted"] = True
                    break

            w.metadata["end_time"] = time.time()
            image = p.send_image()
            if image is not None:
                w.add_blob("plot.png", image)
                display.display(display.Image(data=image, format="png"))
        duration = w.metadata["end_time"] - w.metadata["start_time"]
        self.logger.info(f"Completed in {_sec_to_str(duration)}")
        self.logger.info(f"Data saved in {w.datapath}")

        return SweepResult(self._basedir, w.id, cast(Metadata, w.metadata), w.datapath)

    @_interruptible
    def sweep(
        self, param: Parameter, setpoints: Setpoints, delay: float = 0.0
    ) -> SweepResult:
        self._check_interrupted()
        with (
            self._sweep_context(),
            sweep.db.Writer(self._basedir) as w,
            self._plotter as p,
        ):
            self.logger.info(f"Starting sweep with ID {w.id}")
            self.logger.debug(f"Sweeping: {param.full_name}")
            self.logger.info(f"Minimum duration {_sec_to_str(len(setpoints) * delay)}")

            self._init_metadata(
                w,
                type="1D",
                function="sweep",
                delay=delay,
                param=param.full_name,
                columns=["time", param.full_name] + self._col_names(),
                setpoints=list(setpoints),
            )
            p.set_cols(w.metadata["columns"])

            for setpoint in tqdm(setpoints):
                param(setpoint)
                time.sleep(delay)

                self._run_run_befores(
                    station=self,
                    writer=w,
                )

                data = [time.time(), setpoint] + self._measure()
                w.add_point(data)
                p.add_point(data)

                self._run_run_afters(
                    station=self,
                    data=data,
                    writer=w,
                )

                if self._should_stop():
                    self.logger.warning(f"ID {w.id} INTERRUPTED")
                    self._interrupted = True
                    w.metadata["interrupted"] = True
                    break

            w.metadata["end_time"] = time.time()
            image = p.send_image()
            if image is not None:
                w.add_blob("plot.png", image)
                display.display(display.Image(data=image, format="png"))

        duration = w.metadata["end_time"] - w.metadata["start_time"]
        self.logger.info(f"Completed in {_sec_to_str(duration)}")
        self.logger.info(f"Data saved in {w.datapath}")

        return SweepResult(self._basedir, w.id, cast(Metadata, w.metadata), w.datapath)

    @_interruptible
    def multisweep(
        self,
        params: list[Parameter],
        setpointslist: list[Setpoints],
        delay: float = 0.0,
    ) -> SweepResult:
        self._check_interrupted()
        if not all(len(sp) == len(setpointslist[0]) for sp in setpointslist):
            raise ValueError("not all setpoint lists have same length!")

        setpoints = [list(i) for i in zip(*setpointslist)]
        with (
            self._sweep_context(),
            sweep.db.Writer(self._basedir) as w,
            self._plotter as p,
        ):
            self.logger.info(f"Starting multisweep with ID {w.id}")
            paramlist: list[str] = []
            for param in params:
                paramlist.append(param.full_name)
            self.logger.debug(f"Sweeping: {paramlist}")
            self.logger.info(f"Minimum duration {_sec_to_str(len(setpoints) * delay)}")

            self._init_metadata(
                w,
                type="1D",
                function="multisweep",
                delay=delay,
                params=paramlist,
                columns=["time"] + paramlist + self._col_names(),
                setpoints=[list(sps) for sps in setpointslist],
            )
            p.set_cols(w.metadata["columns"])

            for setpoint in tqdm(setpoints):
                for param, sp in zip(params, setpoint):
                    param(sp)
                time.sleep(delay)

                self._run_run_befores(
                    station=self,
                    writer=w,
                )

                data = [time.time()] + setpoint + self._measure()
                w.add_point(data)
                p.add_point(data)

                self._run_run_afters(
                    station=self,
                    data=data,
                    writer=w,
                )

                if self._should_stop():
                    self.logger.warning(f"ID {w.id} INTERRUPTED")
                    self._interrupted = True
                    w.metadata["interrupted"] = True
                    break

            w.metadata["end_time"] = time.time()
            image = p.send_image()
            if image is not None:
                w.add_blob("plot.png", image)
                display.display(display.Image(data=image, format="png"))

        duration = w.metadata["end_time"] - w.metadata["start_time"]
        self.logger.info(f"Completed in {_sec_to_str(duration)}")
        self.logger.info(f"Data saved in {w.datapath}")

        return SweepResult(self._basedir, w.id, cast(Metadata, w.metadata), w.datapath)

    @_interruptible
    def megasweep(
        self,
        slow_param: Parameter,
        slow_v: Setpoints,
        fast_param: Parameter,
        fast_v: Setpoints,
        slow_delay: float = 0.0,
        fast_delay: float = 0.0,
        init_delay: bool = True,
    ) -> SweepResult:
        self._check_interrupted()
        with (
            self._sweep_context(),
            sweep.db.Writer(self._basedir) as w,
            self._plotter as p,
        ):
            self.logger.info(f"Starting megasweep with ID {w.id}")
            self.logger.debug(
                f"Slow: {slow_param.full_name}, Fast: {fast_param.full_name}"
            )
            min_duration = (
                len(slow_v) * len(fast_v) * fast_delay + len(slow_v) * slow_delay
            )
            self.logger.info(f"Minimum duration {_sec_to_str(min_duration)}")

            self._init_metadata(
                w,
                type="2D",
                function="megasweep",
                slow_delay=slow_delay,
                fast_delay=fast_delay,
                slow_param=slow_param.full_name,
                fast_param=fast_param.full_name,
                columns=[
                    "time",
                    slow_param.full_name,
                    fast_param.full_name,
                ]
                + self._col_names(),
                slow_setpoints=list(slow_v),
                fast_setpoints=list(fast_v),
            )
            p.set_cols(w.metadata["columns"])

            for i, ov in enumerate(tqdm(slow_v, position=0)):
                self.logger.debug(
                    f"{i + 1}/{len(slow_v)}: {slow_param.full_name}= {ov}"
                )
                slow_param(ov)

                for j, iv in enumerate(tqdm(fast_v, position=1, leave=False)):
                    fast_param(iv)
                    if not init_delay and i == 0 and j == 0:
                        pass
                    elif j == 0:
                        interruptible_sleep(
                            slow_delay,
                            show_progress=False,
                            should_stop=self._should_stop,
                        )

                    if self._should_stop():
                        self.logger.warning(f"ID {w.id} INTERRUPTED")
                        self._interrupted = True
                        w.metadata["interrupted"] = True
                        break

                    time.sleep(fast_delay)

                    self._run_run_befores(
                        station=self,
                        writer=w,
                    )
                    data = [time.time(), ov, iv] + self._measure()
                    w.add_point(data)
                    p.add_point(data)

                    self._run_run_afters(
                        station=self,
                        data=data,
                        writer=w,
                    )

                    if self._should_stop():
                        self.logger.warning(f"ID {w.id} INTERRUPTED")
                        self._interrupted = True
                        w.metadata["interrupted"] = True
                        break

                if self._should_stop():
                    self.logger.warning(f"ID {w.id} INTERRUPTED")
                    self._interrupted = True
                    w.metadata["interrupted"] = True
                    break

            w.metadata["end_time"] = time.time()
            image = p.send_image()
            if image is not None:
                w.add_blob("plot.png", image)
                display.display(display.Image(data=image, format="png"))

        duration = w.metadata["end_time"] - w.metadata["start_time"]
        self.logger.info(f"Completed in {_sec_to_str(duration)}")
        self.logger.info(f"Data saved in {w.datapath}")

        return SweepResult(self._basedir, w.id, cast(Metadata, w.metadata), w.datapath)

    @_interruptible
    def multimegasweep(
        self,
        slow_params: list[Parameter],
        slow_v_list: list[Setpoints],
        fast_params: list[Parameter],
        fast_v_list: list[Setpoints],
        slow_delay: float = 0.0,
        fast_delay: float = 0.0,
        init_delay: bool = True,
    ) -> SweepResult:
        self._check_interrupted()
        if not all(len(sp) == len(fast_v_list[0]) for sp in fast_v_list):
            raise ValueError("not all fast axis setpoint lists have same length!")
        if not all(len(sp) == len(slow_v_list[0]) for sp in slow_v_list):
            raise ValueError("not all slow axis setpoint lists have same length!")

        slow_vs = [list(i) for i in zip(*slow_v_list)]
        fast_vs = [list(i) for i in zip(*fast_v_list)]

        with (
            self._sweep_context(),
            sweep.db.Writer(self._basedir) as w,
            self._plotter as p,
        ):
            self.logger.info(f"Starting multimegasweep with ID {w.id}")
            slowparamlist: list[str] = []
            for param in slow_params:
                slowparamlist.append(param.full_name)

            fastparamlist: list[str] = []
            for param in fast_params:
                fastparamlist.append(param.full_name)

            self.logger.debug(f"Slows: {slowparamlist}, Fasts: {fastparamlist}")
            min_duration = (
                len(slow_vs) * len(fast_vs) * fast_delay + len(slow_vs) * slow_delay
            )
            self.logger.info(f"Minimum duration {_sec_to_str(min_duration)}")

            self._init_metadata(
                w,
                type="2D",
                function="multimegasweep",
                slow_delay=slow_delay,
                fast_delay=fast_delay,
                slow_params=slowparamlist,
                fast_params=fastparamlist,
                columns=["time"] + slowparamlist + fastparamlist + self._col_names(),
                slow_setpoints=[list(sps) for sps in slow_v_list],
                fast_setpoints=[list(sps) for sps in fast_v_list],
            )
            p.set_cols(w.metadata["columns"])

            for i, slow_v in enumerate(tqdm(slow_vs, position=0)):
                self.logger.debug(f"{i + 1}/{len(slow_vs)}: {slowparamlist} = {slow_v}")
                for slow_param, ov in zip(slow_params, slow_v):
                    slow_param(ov)

                for j, fast_v in enumerate(tqdm(fast_vs, position=1, leave=False)):
                    for fast_param, iv in zip(fast_params, fast_v):
                        fast_param(iv)

                    if not init_delay and i == 0 and j == 0:
                        pass
                    elif j == 0:
                        interruptible_sleep(
                            slow_delay,
                            show_progress=False,
                            should_stop=self._should_stop,
                        )

                    if self._should_stop():
                        self.logger.warning(f"ID {w.id} INTERRUPTED")
                        self._interrupted = True
                        w.metadata["interrupted"] = True
                        break

                    time.sleep(fast_delay)

                    self._run_run_befores(
                        station=self,
                        writer=w,
                    )

                    data = [time.time()] + slow_v + fast_v + self._measure()
                    w.add_point(data)
                    p.add_point(data)

                    self._run_run_afters(
                        station=self,
                        data=data,
                        writer=w,
                    )

                    if self._should_stop():
                        self.logger.warning(f"ID {w.id} INTERRUPTED")
                        self._interrupted = True
                        w.metadata["interrupted"] = True
                        break

                if self._should_stop():
                    self.logger.warning(f"ID {w.id} INTERRUPTED")
                    self._interrupted = True
                    w.metadata["interrupted"] = True
                    break

            w.metadata["end_time"] = time.time()
            image = p.send_image()
            if image is not None:
                w.add_blob("plot.png", image)
                display.display(display.Image(data=image, format="png"))

        duration = w.metadata["end_time"] - w.metadata["start_time"]
        self.logger.info(f"Completed in {_sec_to_str(duration)}")
        self.logger.info(f"Data saved in {w.datapath}")

        return SweepResult(self._basedir, w.id, cast(Metadata, w.metadata), w.datapath)


class AsyncStation(Station):
    """
    AsyncStation is an asynchronous version of the Station class. It allows users to follow parameters
    and perform measurements asynchronously without changing the I/O interface. Parameters are grouped
    according to their instrument, so that a given instrument can be handled sychronously.

    Attributes:
        _ps_by_inst (defaultdict): A dictionary mapping instruments to their respective parameters.
        _gains_by_inst (defaultdict): A dictionary mapping instruments to their respective gains.
        _params (list): A list of tuples containing parameters and their corresponding gains.

    Methods:
        follow_param(param, gain=1.0):
            Adds a parameter to be followed with an optional gain.
            Alias: fp

        _measure_by_inst(ps):
            Measures the values of the given parameters.
    """

    def __init__(
        self,
        measurement_config: dict[str, str] | None = None,
        basedir: str | None = None,
        verbose: bool = True,
    ) -> None:
        self._ps_by_inst: defaultdict[InstrumentBase | None, list[Parameter]] = (
            defaultdict(list)
        )
        self._gains_by_inst: defaultdict[InstrumentBase | None, list[float]] = (
            defaultdict(list)
        )
        self._params: list[ParamGain] = []
        self._executor: concurrent.futures.ThreadPoolExecutor | None = None
        super().__init__(measurement_config, basedir, verbose)

    @contextlib.contextmanager
    def _sweep_context(self) -> Iterator[None]:
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=len(self._ps_by_inst)
        )
        try:
            yield
        finally:
            self._executor.shutdown(wait=True)
            self._executor = None

    def follow_param(self, param: Parameter, gain: float = 1.0) -> "AsyncStation":
        self._params.append((param, gain))
        self.logger.debug(f"Follow parameter: {param.full_name}, gain: {gain}")
        self._ps_by_inst[param.instrument].append(param)
        self._gains_by_inst[param.instrument].append(gain)
        return self

    fp = follow_param

    def _measure_by_inst(self, ps: list[Parameter]) -> list[float]:
        batch_result = self._try_batch_read(ps)
        if batch_result is not None:
            return batch_result
        return [p() for p in ps]

    def _try_batch_read(self, ps: list[Parameter]) -> list[float] | None:
        """Attempt a coherent batch read if the instrument supports it."""
        if len(ps) < 2:
            return None

        inst = ps[0].instrument
        if inst is None:
            return None

        names = [p.name for p in ps]

        # SR830-style: SNAP? (case-insensitive, 2-6 params)
        if isinstance(inst, SnapReadable) and len(ps) <= 6:
            if all(n.lower() in inst.SNAP_PARAMETERS for n in names):
                return list(inst.snap(*names))

        # SR86x-style: get_values (case-sensitive, 2-3 params)
        if isinstance(inst, BatchReadable) and len(ps) <= 3:
            if all(n in inst.PARAMETER_NAMES for n in names):
                return list(inst.get_values(*names))

        return None

    @contextlib.contextmanager
    def _ensure_executor(self) -> Iterator[concurrent.futures.ThreadPoolExecutor]:
        if self._executor is not None:
            yield self._executor
        else:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=len(self._ps_by_inst)
            ) as executor:
                yield executor

    def _measure(self) -> list[float]:
        with self._ensure_executor() as executor:
            futs_by_inst: dict[
                InstrumentBase | None, concurrent.futures.Future[list[float]]
            ] = {}
            for i, ps in self._ps_by_inst.items():
                futs_by_inst[i] = executor.submit(self._measure_by_inst, ps)

            ret: dict[Parameter, float] = {}
            for future, ps in zip(futs_by_inst.values(), self._ps_by_inst.values()):
                results = future.result()
                for res, p in zip(results, ps):
                    ret[p] = res

        return [ret[p] / gain for p, gain in self._params]
